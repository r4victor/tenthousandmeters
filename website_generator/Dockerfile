FROM python:3.9-alpine

WORKDIR /ttm/website_generator
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

COPY links_updater links_updater
COPY plugins plugins
COPY themes themes
COPY pelicanconf.py entrypoint.sh ./

RUN chmod +x entrypoint.sh

CMD ["./entrypoint.sh"]