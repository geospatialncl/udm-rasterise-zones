import subprocess
from pathlib import Path
import os
import logging
from osgeo import ogr
import math
import geopandas as gpd
import pandas as pd


# setup paths to data
data = Path(os.getenv('DATA_PATH', '/data'))

inputs = data / 'inputs'

temp = data / 'temp'

outputs = data / 'outputs'

temp.mkdir(exist_ok=True)
outputs.mkdir(exist_ok=True)

sort_field = os.getenv('SORT_FIELD')

logger = logging.getLogger('udm-rasterise-zones')
logger.setLevel(logging.INFO)
fh = logging.FileHandler(outputs / 'udm-rasterise-zones.log')
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
logger.addHandler(fh)

input_files = []
for ext in ['shp', 'gpkg']:
    input_files.extend(list(inputs.glob(f"zones/*.{ext}")))

assert len(input_files) > 0, 'No input files found'
selected_file = input_files[0]

logger.info(f'Calculating extents from {selected_file}')

# Get extension for input file
#ext = input_files[0].split('.')[1]
file_extension = input_files[0].suffix

# Get a Layer's Extent
inShapefile = str(input_files[0])
if file_extension == '.gpkg':
    inDriver = ogr.GetDriverByName("GPKG")
else:
    inDriver = ogr.GetDriverByName("ESRI Shapefile")

inDataSource = inDriver.Open(inShapefile, 0)
inLayer = inDataSource.GetLayer()
extents = inLayer.GetExtent()


# Round minima down and maxima up to nearest km
def round_down_nearest_km(val):
    return math.floor(val / 1000) * 1000


def round_up_nearest_km(val):
    return math.ceil(val / 1000) * 1000


xmin = round_down_nearest_km(extents[0])
ymin = round_down_nearest_km(extents[2])
xmax = round_up_nearest_km(extents[1])
ymax = round_up_nearest_km(extents[3])

print('xmin,ymin,xmax,ymax') 
extent = str(xmin) + ','
extent += str(ymin) + ','
extent += str(xmax) + ','
extent += str(ymax)
print(extent)

f = open(outputs / "extents.txt", "w")
f.write(extent)
f.close()

logger.info('Extents calculated')

# get extent 'xmin,ymin,xmax,ymax'
if extent == 'None' or extent is None:
    extent = []
else:
    extent = ['-te', *extent.split(',')]

logger.info(f'Creating bounding box for {selected_file}')

# Create a Polygon from the extent tuple
ring = ogr.Geometry(ogr.wkbLinearRing)
ring.AddPoint(xmin, ymin)
ring.AddPoint(xmax, ymin)
ring.AddPoint(xmax, ymax)
ring.AddPoint(xmin, ymax)
ring.AddPoint(xmin, ymin)
poly = ogr.Geometry(ogr.wkbPolygon)
poly.AddGeometry(ring)

# Save extent to a new Shapefile
outShapefile = str(outputs / 'extent.shp')
outDriver = ogr.GetDriverByName("ESRI Shapefile")

# Remove output shapefile if it already exists
if os.path.exists(outShapefile):
    outDriver.DeleteDataSource(outShapefile)

# Create the output shapefile
outDataSource = outDriver.CreateDataSource(outShapefile)
outLayer = outDataSource.CreateLayer("extent", geom_type=ogr.wkbPolygon)

# Add an ID field
idField = ogr.FieldDefn("id", ogr.OFTInteger)
outLayer.CreateField(idField)

# Create the feature and set values
featureDefn = outLayer.GetLayerDefn()
feature = ogr.Feature(featureDefn)
feature.SetGeometry(poly)
feature.SetField("id", 1)
outLayer.CreateFeature(feature)
feature = None

# Save and close DataSource
inDataSource = None
outDataSource = None

logger.info('Bounding box created')

# Add the sort_id field and save to temp
boundaries = gpd.read_file(input_files[0]).sort_values(sort_field)
boundaries['sort_id'] = range(len(boundaries))
boundaries.to_file(temp / 'boundaries.shp')

# Merge with population data and store population as CSV
population = pd.read_csv(inputs / 'population/population.csv')
population = boundaries.merge(population).sort_values('sort_id')
assert (population.sort_id.diff().iloc[1:] == 1).all(), 'Population data missing'
population = population.rename(columns={'sort_id': 'zone_identity', sort_field: 'zone_code',
                                        'initial_population': 'initial_value', 'final_population': 'final_value'})

population[['zone_identity', 'zone_code', 'initial_value', 'final_value']].to_csv(outputs / 'population.csv',
                                                                                    index=False)

logger.info(f'Rasterizing {selected_file}')

subprocess.call(['gdal_rasterize',
                 '-a', 'sort_id',  # attribute field to burn
                 '-tr', '100', '100',  # target resolution <xres> <yres>
                 '-co', 'COMPRESS=LZW', '-co', 'NUM_THREADS=ALL_CPUS',  # creation options
                 '-ot', 'Int16',  # output data type
                 '-a_nodata', '-1',   #set nodata value 
                 *extent,  # '-te' <xmin> <ymin> <xmax> <ymax>
                 str(temp / 'boundaries.shp'), str(temp / 'rasterise_zid_100m.tif')])  # src_datasource, dst_filename

logger.info('Rasterizing completed')

# --translate and set nodata to zero

logger.info('Translating raster')

subprocess.call(['gdal_translate',
                 '-tr', '100', '100',    #target resolution <xres> <yres>                
                 '-ot', 'Int16',        #output data type 
                 '-a_nodata', '-1',  # set nodata value
                 str(temp / 'rasterise_zid_100m.tif'), str(outputs / 'zone_identity.asc')])  # srcfile, dstfile

logger.info('Translating completed')
