FROM docker.io/library/python
LABEL org.opencontainers.image.source=https://github.com/Alanaktion/gallery
WORKDIR /app
COPY . .
EXPOSE 8000
CMD ["python", "/app/gallery.py", "/files", "--host", "0.0.0.0"]
