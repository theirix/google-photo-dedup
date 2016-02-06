#!/usr/bin/env python3

import os
import re
import itertools
import argparse
import httplib2
from apiclient import discovery
import oauth2client
from oauth2client import client
from oauth2client import tools

__author__ = 'theirix'
__license__ = 'MIT'
"""
Google Photo Dedup.

Small script for removing duplicate Google Photo uploads.
They may appear when photos of different resolutions were backuped.
Usually these files have same name and/or EXIF create time (do not
confuse with Drive file createdTime) and miss EXIF information.

To actually remove files specify '-d' flag. To see JSONs specify '-v' flag.
Duplicate files are moved to Drive trash.

Before first launch it is needed to setup Drive credentials at developer console
and drop credentials JSON at ~/.config/google-photo-dedup/client_id.json
"""

SCOPES = ['https://www.googleapis.com/auth/drive',
          'https://www.googleapis.com/auth/drive.file',
          'https://www.googleapis.com/auth/drive.metadata',
          'https://www.googleapis.com/auth/drive.photos.readonly']

APPLICATION_NAME = 'Google Photo Dedup'


def get_credentials(flags):
    """Gets valid user credentials from storage.

    If nothing has been stored, or if the stored credentials are invalid,
    the OAuth2 flow is completed to obtain the new credentials.

    Returns:
        Credentials, the obtained credential.
    """
    home_dir = os.path.expanduser('~')
    credential_dir = os.path.join(home_dir, '.config', 'google-photo-dedup')
    if not os.path.exists(credential_dir):
        os.makedirs(credential_dir)
    credential_path = os.path.join(credential_dir, 'auth-cache.json')
    client_secret_path = os.path.join(credential_dir, 'client_id.json')

    store = oauth2client.file.Storage(credential_path)
    credentials = store.get()
    if not credentials or credentials.invalid:
        flow = client.flow_from_clientsecrets(client_secret_path, SCOPES)
        flow.user_agent = APPLICATION_NAME
        if flags:
            credentials = tools.run_flow(flow, store, flags)
        else:  # Needed only for compatibility with Python 2.6
            credentials = tools.run(flow, store)
        print('Storing credentials to ' + credential_path)
    return credentials


def pretty_inspect(file):
    """ :return: pretty file representation """
    return "{} ({}x{}, {} MP, {} KiB), {}".format(
        file.get('name'),
        file.get('imageMediaMetadata').get('width'),
        file.get('imageMediaMetadata').get('height'),
        image_resolution(file) // (1024*1024),
        (int(file.get('size')) // 1024),
        file.get('webViewLink'))

def unique_image_resolution(file):
    """ :return: hashed image resolutions for the Drive file"""
    imm = file.get('imageMediaMetadata')
    return hash((imm.get('width'), imm.get('height')))

def image_resolution(file):
    """ :return: image resolutions for the Drive file"""
    imm = file.get('imageMediaMetadata')
    return imm.get('width') * imm.get('height')

def time_key(file):
    """ :return: 'time' field or None if absent or damaged """
    field = file.get('imageMediaMetadata').get('time')
    if field and len(field) > 5:
        return field
    return None

def group_key(file):
    """ :return: grouping key for finding duplicates """
    if time_key(file):
        return time_key(file)
    # createdTime is not reilable because often it is upload time
    #return file.get('createdTime')
    # instead use drive file name. it perfectly matches our needs
    name = file.get('name')
    # normalize name
    match = re.match(r"IMG_(\d{8})_(\d{6})(.*)", name)
    if match:
        m1, m2, m3 = match.groups()
        name = "{}-{}-{} {}.{}.{}{}".format(m1[0:4], m1[4:6], m1[6:8],
                                            m2[0:2], m2[2:4], m2[4:6], m3)
    return name

def with_camera_model(file):
    """ :return: if camera model is present """
    return file.get('cameraModel') != None and file.get('cameraModel') != ''

def main():
    """
Rules for finding duplicates.
Build equivalence groups by group_key where resolution (WxH) differ
Then leave only these photos where resolution is biggest (better if camera
model specified).
Sometimes different photos can be shoot during one second so they will fall
to the same equivalence group. It is okay because they are exluded due to
the same resolution.
"""
    # For debug purpose:
    # logging.getLogger().setLevel(logging.DEBUG)
    # httplib2.debuglevel = 4

    parser = argparse.ArgumentParser(parents=[tools.argparser])
    parser.add_argument('--verbose', '-v', action='store_true')
    parser.add_argument('--delete', '-d', action='store_true')
    flags = parser.parse_args()

    credentials = get_credentials(flags)
    http = credentials.authorize(httplib2.Http())
    service = discovery.build('drive', 'v3', http=http)

    query = "mimeType='image/jpeg' and trashed=false"
    # query += " and createdTime >= '2016-01-02'"
    # query += " and name contains '2016-01-02'"

    files_list = []
    page_token = None
    page_index = 0

    print("Fetching metadata ", end="")
    while True:
        response = service.files().list(
            q=query,
            spaces='drive',
            fields="nextPageToken," +
            "files(id,name,size,modifiedTime,createdTime,ownedByMe,webViewLink,"
            + "imageMediaMetadata(width,height,cameraModel,time))",
            orderBy='createdTime',
            pageToken=page_token).execute()
        files_list += response.get('files', [])
        page_token = response.get('nextPageToken', None)
        if page_token is None:
            break
        page_index += 1
        print(".", end="", flush=True)

    print("\nFound files: {}, fetched {} pages".format(
        len(files_list), page_index))

    print("Files with 'time' metadata: {}".format(
        len(list(f for f in files_list if time_key(f)))))

    if flags.verbose:
        for file in files_list:
            print(repr(file), "\n")

    # Filter photos
    duplicates_groups = list([k, list(v)]
                             for k, v in itertools.groupby(
                                 sorted(
                                     (f for f in files_list if f.get('ownedByMe') and group_key(f)),
                                     key=group_key),
                                 group_key))
    duplicates_groups = list([key, sorted(duplicates,
                                          key=image_resolution)]
                             for key, duplicates in duplicates_groups
                             if len(duplicates) > 1 and
                             len(set(unique_image_resolution(f) for f in duplicates)) > 1)
    print("Found duplicate groups: {}".format(len(duplicates_groups)))

    # Iterate duplicate groups
    for key, duplicates in duplicates_groups:
        print(
            "\nProcessing duplicates for createdTime {} - {} photo(s)".format(
                key, len(duplicates)))
        prefered = duplicates.pop()

        # Print data
        print("  Prefer: {}".format(pretty_inspect(prefered)))
        if flags.verbose:
            print("  JSON: " + repr(prefered))
        for file in duplicates:
            print("  Delete: {}".format(pretty_inspect(file)))
            if flags.verbose:
                print("  JSON: " + repr(file))

        # Sanity checks
        if not with_camera_model(prefered) and any(with_camera_model(f) for f in duplicates):
            print("Ignore removing duplicates where camera model is set")
            continue
        if int(prefered.get('size')) < min(int(f.get('size')) for f in duplicates):
            print("Ignore removing duplicates larger then prefered")
            continue

        # Delete duplicates
        for file in duplicates:
            if flags.delete:
                service.files().update(fileId=file.get('id'), body={'trashed': True}).execute()

    print("Done")

if __name__ == '__main__':
    main()
