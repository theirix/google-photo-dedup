# Google Photo Deduplication

Small script for removing duplicate Google Photo uploads.
They may appear when photos of different resolutions were backed up.
Usually, these files have the same name and/or EXIF create time (do not
confuse with Drive file createdTime) and miss EXIF information.

To actually remove files, specify `-d` flag. To see JSONs specify `-v` flag.
Duplicate files are moved to the Drive trash.

Before the first launch it is needed to set up Drive credentials at the developer console
and drop credentials JSON at `~/.config/google-photo-dedup/client_id.json`.

Please beware of splitting Google Photo and Google Drive into two separate products. The script will find only photos stored in
Google Drive. Photos uploaded since the split will not be stored in Google Drive and will not be detected by the script.

*WARNING! Please use carefully and always check what is deleting, especially with '--delete' flag*

## Requirements

Python3 and [API Client Library](https://developers.google.com/api-client-library/python/start/installation).
In short launch:

		pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib

Also, you need `client_id.json` from the developer console to be placed at
`~/.config/google-photo-dedup/client_id.json` or `%USERPROFILE%\.config\google-photo-dedup\client_id.json`

## Usage

Check duplicates:

		python3 google-photo-dedup.py

Remove duplicates:

		python3 google-photo-dedup.py -d

Additional mode with fuzzy search (for example, treat as same files
`IMG_20121108_144554.jpg` and `2012-11-08 14.45.53.jpg`) with maximum time delta of one second:

		python3 google-photo-dedup.py -m -d

## Rationale

The script solves the very specific problem with repeated uploading same files.  The script cannot help with a more general case when it’s needed to find photo duplicates based on their content. It’s up to specialized photo tools or organizers.

I wrote it to handle the case when the Google Photo application started to repeatedly upload local files from my Android phone. Somehow they broke their algorithm for detecting whether the local photo was uploaded, so the Google Photo contained thousands of photos but with names that may be the same or differ by a second. This case became worse when Google Photo applied compression to photos, so I could not distinguish photos just by their size. And the last problem was that a filename does not always reflect created time of the photo, which is encoded to EXIF and can be extracted only by API. So the only way to clean up duplicates was to group photos by their created time or filename with small variations and keep only one photo from the group by the heuristic criteria (photo resolution or size). Photo groups must be visually inspected before actual deleting because false positives are very common.

False positives for the script can include:

1. Cropped photos - actual and cropped photos will have the same created time.
  The script suggests keeping a photo with a larger resolution, but it is only a suggestion that must be checked.

2. Manually uploaded photos.
  The script does not know about them and probably will put them in one group. All but one photos will be selected for deletion. Most probably, it is not what you want. So the script does not handle this case correctly and can delete unaffected files.


## License

MIT
