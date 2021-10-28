FROM osgeo/gdal:ubuntu-small-3.3.2

RUN mkdir /src

WORKDIR /src

COPY script.py .

RUN apt update && apt install -y python3-pip && pip install geopandas

CMD python script.py
