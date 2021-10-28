FROM osgeo/gdal:alpine-normal-3.2.0

RUN mkdir /src

WORKDIR /src

COPY script.py .

CMD python script.py
