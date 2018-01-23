# JinstaScrape
A lightweight, concurrent and extensible Instagram scraper for computer science research!
--
## About
This Instagram scraper takes reference from [Instagram Scraper](https://github.com/rarcega/instagram-scraper/graphs/contributors), a project created by [@rarcega](https://github.com/rarcega).
In research, we are often more interested in collecting posts based on entire lists of qualifying hashtags and locations than in exhaustively scraping from individual profiles. What started out as a modification of [Instagram Scraper](https://github.com/rarcega/instagram-scraper/graphs/contributors) ended up being almost a complete rework to achieve the following:
* Scrape based on a given list of hashtags
* Scrape based on a given list of locations (not yet implemented)
* Do not re-scrape a post that was previously scraped from another search term in the list
* Collect all information about a post and save them in a centralized manifest on disk where they can be retrieved via the post's shortcode
* Downloading of media only comes in as an additional step after the manifest has been completely written
* Saves current scraped information when user sends keyboard interrupt so that scaped posts will not be re-scraped in the future
* Provide an easy-to-follow, well-documented and extensible codebase so that anyone could make suitable modifications to suit their own research approaches

## Credits
As you inspect the code, you may notice that some methods and variable naming were carried over from [Instagram Scraper](https://github.com/rarcega/instagram-scraper/graphs/contributors). In such cases, the credit for them goes entirely to their original authors from [Instagram Scraper](https://github.com/rarcega/instagram-scraper/graphs/contributors). I have also mostly employed the same libraries and packages that [Instagram Scraper](https://github.com/rarcega/instagram-scraper/graphs/contributors) utilized.

## Why not use Instagram's API?
[Instagram's Rate Limits](https://www.instagram.com/developer/limits/). However, when you pretend to be a browser loading the pages you can overcome that. Well okay I lied, you can't overcome [HTTP 429](https://httpstatuses.com/429) entirely but you're able to deal with it far better as a scraper than as a live app. I didn't have the time to verify this in a more empricial fashion so if you'd like to do an actual experiment, please do and let me know! :)

## How it works
Here is a sample command using all the available options (*see following section for option details*).
```sh
python jinstascrape.py -sbh True -hp ./hashtags.txt -mp ./manifest.json -d True -dd ./downloads
```
Steps:
1. Read in manifest. Creates an empty one if non-existent
2. (if `-sbh True`) Read in `./hashtags.txt` as a list of hashtags to query
3. For each hashtag
    1. Query for the posts tagged with them. [Example](https://www.instagram.com/graphql/query/?query_id=17882293912014529&tag_name=allyourbasearebelongstous&first=100&after=)
    2. For each post, check for shortcode in manifest
    3. If not previously scraped (i.e. not in manifest), query media page. [Example](https://www.instagram.com/p/BK82TOvDYI-/?__a=1)
    4. Format post information and add it to manifest
4. Saves manifest to disk at `./manifest.json`   
5. (if `-d True`) For each post in manifest
    1. Download the media via their urls to `./downloads`
    2. Update post media in manifest with their downloaded location
6. Saves updated manifest to disk at `./manifest.json`

## Options
| Shortform | Longform | Default | Details |
| --- | --- | --- | --- |
| `-sbh` | `--scrape-by-hashtags` | `True` | Indicates if scraping by hashtags |
| `-hp` | `--hashtags-path` | `./hashtags.txt` | Path for text file containing list of hashtags to scrape |
| `-mp` | `--manifest-path` | `./manifest.json` | Path for JSON manifest file |
| `-d` | `--download` | `False` | Download the images and videos |
| `-dd` | `--downloads-directory` | `./downloads` | Downloads directory |

## Manifest
Format:
```json
{
  "AbCdeF_G0hI": {
    "__typename": "GraphSidecar",
    "id": "1234567890123456789",
    "shortcode": "AbCdeF_G0hI",
    "is_video": false,
    "taken_at_timestamp": 1234567890,
    "last_scraped_at": "2018-01-19 12:16:04.334173",
    "is_ad": false,
    "location": {
      "slug": "some-grand-place",
      "id": "1234567890",
      "name": "Some Grand Place",
      "has_public_page": true     
    },
    "owner": {
      "id": 123456,
      "profile_pic_url": "https://scontent-sin6-1.cdninstagram.com/t51.2885-19/10593517_501208056648267_1283747068.jpg",
      "username": "John",
      "full_name": "John Doe",
      "is_private": false,
      "is_unpublished": false,
      "is_verified": false
    },
    "media": [
      {
        "__typename": "GraphImage",
        "shortcode": "AbCdeF_G0hI",
        "id": "0123456789012345678",
        "downloaded_path": "./downloads/26269367_1740684259304656_5998716977634344960.jpg"
      },
      ...
    ]  
  }
  ...
}
```

## Remaining work
You are more than welcome to contribute to this project! Who knows? Maybe it will end up being much more than what it set out to be!
* Complete query by location procedure
* Refactor instagram post as a Python class on its own
* Write tests

## License
This is free and unencumbered software released into the public domain.

Anyone is free to copy, modify, publish, use, compile, sell, or distribute this software, either in source code form or as a compiled binary, for any purpose, commercial or non-commercial, and by any means.

In jurisdictions that recognize copyright laws, the author or authors of this software dedicate any and all copyright interest in the software to the public domain. We make this dedication for the benefit of the public at large and to the detriment of our heirs and successors. We intend this dedication to be an overt act of relinquishment in perpetuity of all present and future rights to this software under copyright law.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
