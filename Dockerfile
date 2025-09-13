FROM docker.io/library/python

WORKDIR /usr/src/app
RUN pip install --no-cache-dir Pillow python-dotenv

COPY gallery.py .

ENV GALLERY_HOST=0.0.0.0
ENV GALLERY_PORT=8000
ENV GALLERY_DIRECTORY=/gallery
EXPOSE 8000
CMD [ "python", "./gallery.py" ]
