# Google Photo Deduplication

Small script for removing duplicate Google Photo uploads.
They may appear when photos of different resolutions were backuped.
Usually these files have the same name and/or EXIF create time (do not
confuse with Drive file createdTime) and miss EXIF information.

To actually remove files specify `-d` flag. To see JSONs specify `-v` flag.
Duplicate files are moved to the Drive trash.

Before first launch it is needed to setup Drive credentials at developer console
and drop credentials JSON at `~/.config/google-photo-dedup/client_id.json`.

Please use carefully and always check what is deleting.

## Requirements

Python3 and [API Client Library](https://developers.google.com/api-client-library/python/start/installation).
In short launch:

		pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib 

Also you need `client_id.json` from the developer console to be placed at 
`~/.config/google-photo-dedup/client_id.json`

## Usage

Check duplicates:

		python3 google-photo-dedup.rb

Remove duplicates:

		python3 google-photo-dedup.rb -d

Additional mode with fuzzy search (for example treat as same files
`IMG_20121108_144554.jpg` and `2012-11-08 14.45.53.jpg`) with maximum time delta of one second:

		python3 google-photo-dedup.rb -m -d

## License

MIT
