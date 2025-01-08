# tenthousandmeters.com

## Overview

The repository contains the source code and contents for my blog [tenthousandmeters.com](https://tenthousandmeters.com). It started as a private repo but now (January 2025) I'm making it public so that everyone can make PRs and issues and contribute.

The blog is generated with [Pelican](https://github.com/getpelican/pelican). The generated HTML then served using [nginx-le](https://github.com/nginx-le/nginx-le) deployed as a Docker container. I've set it up in 2020 and it's been working ever since.

## Running

Building the website and running it locally should be as simple as:

```bash
docker compose -f docker-compose.yaml up
```

To have a live reload as you edit the Markdown files, you can install the Python dependencies locally and run `pelican -r` from the `website_generator` dir.

## Contributing

If you noticed a typo, feel free to open a PR. If you noticed some factual mistakes or want to make an improvement, consider opening an issue. The posts are not supposed to be edited but I add update notes when it's appropriate.
