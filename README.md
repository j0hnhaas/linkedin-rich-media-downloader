# LinkedIn Rich Media Downloader

A small open-source utility for downloading and preserving the images and videos referenced in LinkedIn's **Rich_Media.csv** data export.

LinkedIn allows users to request an export of their account data. Depending on the export, it can include a file called **Rich_Media.csv**. That CSV contains metadata about media uploaded to LinkedIn and, for many entries, a direct **Media Link** to the corresponding image or video.

The problem is simple: opening hundreds of those links and saving the files by hand is tedious, error-prone, and unnecessary.

**LinkedIn Rich Media Downloader automates that job.**

## Why this exists

A LinkedIn data export is useful for preserving your own activity, but the rich-media export does not necessarily arrive as a convenient local folder containing every image and video.

Instead, Rich_Media.csv may contain direct links to files hosted on LinkedIn's CDN.

For an account with dozens or hundreds of media items, downloading each file manually means:

- opening one URL after another
- saving every image or video individually
- keeping track of which items were already downloaded
- dealing with missing or expired links
- manually documenting failures

This script does all of that automatically.

There is also a time factor: CDN links can be signed or temporary. A link that works today may no longer work later. If you want to preserve your own LinkedIn media archive, it therefore makes sense to download the files soon after receiving the export.

## What it does

The script:

- reads LinkedIn's Rich_Media.csv
- processes the Media Link column
- downloads reachable images and videos
- detects the file extension from the HTTP Content-Type
- creates stable, readable filenames based on upload date, time, and media type
- skips files that have already been downloaded
- retries temporary failures
- calculates a SHA-256 checksum for every successfully preserved file
- creates a manifest.csv documenting the download
- records missing links and failures instead of silently ignoring them

The original Rich_Media.csv is never modified.

## Example

Input:

    Rich_Media.csv

Output:

    linkedin-rich-media/
    ├── 2026-09-24_16-00-00_feed-photo_0001.jpg
    ├── 2026-09-20_20-53-00_feed-photo_0002.jpg
    ├── 2026-09-19_15-06-00_feed-photo_0003.jpg
    ├── ...
    └── manifest.csv

## Requirements

- Python 3.9 or newer recommended
- requests

Install the dependency with:

    pip install -r requirements.txt

or:

    pip install requests

## Usage

Clone or download this repository and run:

    python linkedin_rich_media_download.py "/path/to/Rich_Media.csv"

By default, the script creates a folder named **linkedin-rich-media** next to the CSV file.

### Windows example

    python linkedin_rich_media_download.py "C:\LinkedIn-Export\Rich_Media.csv"

### macOS / Linux example

    python3 linkedin_rich_media_download.py ~/Downloads/linkedin-export/Rich_Media.csv

## Choose a different destination

Provide a second argument:

    python linkedin_rich_media_download.py "/path/to/Rich_Media.csv" "/path/to/archive"

Windows example:

    python linkedin_rich_media_download.py "C:\LinkedIn-Export\Rich_Media.csv" "D:\Archives\linkedin-rich-media"

## Safe to run again

The downloader is designed to be restartable.

If the process is interrupted, simply run the same command again. Existing files are skipped unless you explicitly use:

    --overwrite

## Command-line options

    --timeout SECONDS
        HTTP timeout per request. Default: 60

    --retries NUMBER
        Number of attempts per media file. Default: 3

    --delay SECONDS
        Pause between downloads. Default: 0.25

    --overwrite
        Replace files that already exist.

Example:

    python linkedin_rich_media_download.py Rich_Media.csv --retries 5 --delay 0.5

## The manifest

Every run creates **manifest.csv**.

It records information including:

- original LinkedIn date/time
- media type
- media description
- original source URL
- local filename
- detected content type
- downloaded file size
- SHA-256 checksum
- HTTP status
- download status
- error message, if any

Typical statuses are:

- downloaded
- already_exists
- no_media_link
- failed

This makes it easy to verify what was successfully archived and what may need attention.

## Important: download sooner rather than later

Media links in Rich_Media.csv can point directly to files hosted on LinkedIn's CDN.

Such links may expire or otherwise stop working. This tool cannot recover a media file after LinkedIn stops serving it through the exported URL.

If preserving your own archive matters to you, run the downloader soon after receiving the data export.

## Where do I get Rich_Media.csv?

Request a copy of your data using LinkedIn's account data export feature. Depending on the export selected and the data available for your account, the resulting archive may contain Rich_Media.csv.

LinkedIn may change its export format over time.

## Privacy

The script runs locally on your computer.

It does not upload your LinkedIn export, media descriptions, downloaded files, or manifest to another service. Network requests are made only to the media URLs contained in your own CSV file.

Your LinkedIn data export may contain personal information. Do not commit your personal Rich_Media.csv, downloaded media, or generated manifest to a public repository unless you intentionally want to publish that information.

## Limitations

- Only rows with a usable Media Link can be downloaded.
- Expired or revoked URLs cannot be recovered by this tool.
- LinkedIn may change the Rich_Media.csv format.
- The script downloads the representation served by the exported URL and cannot guarantee that it is the original-resolution upload.
- Some rows may contain metadata but no downloadable media URL.

## Scope

This project is intentionally small.

It is **not** a LinkedIn scraper and does not attempt to bypass authentication or access controls. It simply automates the download of media URLs supplied by LinkedIn as part of a user's own account data export.

## Disclaimer

This is an unofficial open-source project and is not affiliated with, endorsed by, or sponsored by LinkedIn.

LinkedIn is a trademark of LinkedIn Corporation and its affiliates.
