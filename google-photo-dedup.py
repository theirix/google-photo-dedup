#!/usr/bin/env python3

import os
import re
import time
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
    return file.get('name')

def with_camera_model(file):
    """ :return: if camera model is present """
    return file.get('cameraModel') != None and file.get('cameraModel') != ''

def process_group(prefered, duplicates, service, flags):
    ever_deleted = False

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
        return False
    if int(prefered.get('size')) < min(int(f.get('size')) for f in duplicates):
        print("Ignore removing duplicates larger then prefered")
        return False

    # Delete duplicates
    for file in duplicates:
        if flags.delete:
            service.files().update(fileId=file.get('id'), body={'trashed': True}).execute()
            ever_deleted = True

    return ever_deleted


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
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='explain what is going on')
    parser.add_argument('--delete', '-d', action='store_true',
                        help='actually delete things')
    parser.add_argument('--renamed', '-m', action='store_true',
                        help='enable mode with fuzzy renamed search')
    parser.add_argument('--query', '-q',
                        help='additional API query')
    flags = parser.parse_args()

    credentials = get_credentials(flags)
    http = credentials.authorize(httplib2.Http())
    service = discovery.build('drive', 'v3', http=http)

    query = "mimeType='image/jpeg' and trashed=false"
    # query += " and createdTime >= '2016-01-02'"
    # query += " and name contains '2016-01-02'"
    # query += " and name contains '2012-05-21'"
    # query += " and (name contains '20120513_' or name contains '2012_05_13')"
    if flags.query and len(flags.query) > 0:
        query += " " + flags.query

    files_list = []
    page_token = None
    page_index = 0

    if flags.delete:
        print("DELETE mode")

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

    files_list = list(f for f in files_list if f.get('ownedByMe'))

    # Filter photos
    print("Stage 1: searching for duplicates by name groups")
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
    ever_deleted = False
    for key, duplicates in duplicates_groups:
        print(
            "\nProcessing duplicates for createdTime {} - {} photo(s)".format(
                key, len(duplicates)))
        prefered = duplicates.pop()
        if process_group(prefered, duplicates, service, flags):
            ever_deleted = True

    # Iterate by small time steps
    if not ever_deleted and flags.renamed:
        print("Stage 2: searching for duplicates by fuzzy name search")
        for file in files_list:
            name = file.get('name')
            match = re.match(r"^(\d{4})-(\d{2})-(\d{2}) (\d{2})\.(\d{2})\.(\d{2})(.*)", name)
            if match:
                m = match.groups()
                name_time = time.mktime((int(m[0]), int(m[1]), int(m[2]),
                                         int(m[3]), int(m[4]), int(m[5]), 0, 0, 0))
                for delta in [-1, 0, +1]:
                    duplicate_name = time.strftime("IMG_%Y%m%d_%H%M%S",
                                                   time.localtime(name_time+delta)) + m[6]
                    duplicates = list(dfile for dfile in files_list if
                                      dfile.get('name') == duplicate_name and
                                      image_resolution(dfile) < image_resolution(file))
                    if len(duplicates) > 0:
                        print("\nProcessing duplicates for name {} and time delta={}".format(
                            name, delta))
                        process_group(file, duplicates, service, flags)


    print("Done")

if __name__ == '__main__':
    main()
