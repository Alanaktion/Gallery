FROM docker.io/library/python

WORKDIR /usr/src/app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libheif1 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir Pillow python-dotenv pi-heif

COPY gallery.py .

ENV GALLERY_HOST=0.0.0.0
ENV GALLERY_PORT=8000
ENV GALLERY_DIRECTORY=/gallery
ENV THUMBNAIL_DIRECTORY=/thm
EXPOSE 8000
VOLUME [ "/gallery" ]
VOLUME [ "/thm" ]
CMD [ "python", "./gallery.py" ]
