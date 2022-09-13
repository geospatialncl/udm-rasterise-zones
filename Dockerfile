FROM osgeo/gdal:ubuntu-small-3.3.2

RUN mkdir /src

WORKDIR /src

RUN apt update && apt install -y python3-pip && pip install geopandas

COPY script.py .

CMD python script.py
