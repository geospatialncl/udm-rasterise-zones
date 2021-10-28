import subprocess
from pathlib import Path
import os
import logging
from osgeo import ogr
import math

#configure directory/subdirectories
current_dir = str(Path.cwd())
#print(current_dir)
inputs = Path(current_dir + '/data/inputs/')
#print(inputs)
temp = Path(current_dir + '/data/temp/')
#print(temp)
outputs = Path(current_dir + '/data/outputs/')
#print(outputs)
temp.mkdir(exist_ok=True)
outputs.mkdir(exist_ok=True)

#configure output log
logger = logging.getLogger('udm-rasterise-zones')
logger.setLevel(logging.INFO)
fh = logging.FileHandler(outputs / 'udm-rasterise-zones.log')
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
logger.addHandler(fh)

#get input polygons
input_files = []
for ext in ['shp', 'gpkg']:
    input_files.extend(list(inputs.glob(f"*/*.{ext}")))

assert len(input_files) > 0, 'No input files found'
selected_file = input_files[0]

#--

logger.info(f'Calculating extents from {selected_file}')

# Get a Layer's Extent
inShapefile = str(input_files[0])
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

# Todo - save extent to file or environment variable
f = open(outputs / "extents.txt", "w")
f.write(extent)
f.close()

logger.info('Extents calculated')

#get extent 'xmin,ymin,xmax,ymax'
#extent = v.get_extent()
if extent == 'None' or extent is None:
    extent = []
else:
    extent = ['-te', *extent.split(',')]

##--

logger.info(f'Creating bounding box for {selected_file}')

# Create a Polygon from the extent tuple
ring = ogr.Geometry(ogr.wkbLinearRing)
ring.AddPoint(xmin,ymin)
ring.AddPoint(xmax,ymin)
ring.AddPoint(xmax,ymax)
ring.AddPoint(xmin,ymax)
ring.AddPoint(xmin,ymin)
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

##--rasterise at 1m

logger.info(f'Rasterizing {selected_file}')

subprocess.call(['gdal_rasterize',
                 '-a', 'zid',		#attribute field to burn 
                 '-tr', '100', '100',	#target resolution <xres> <yres>
                 '-co', 'COMPRESS=LZW', '-co', 'NUM_THREADS=ALL_CPUS',	#creation options
                 '-ot', 'UInt16',	#output data type                 
                 *extent,			#'-te' <xmin> <ymin> <xmax> <ymax> 
                 selected_file, temp / 'rasterise_zid_100m.tif'])	#src_datasource, dst_filename

logger.info('Rasterizing completed')

##--mode reasmple to 100m

#logger.info('Mode resampling raster')

#subprocess.call(['gdalwarp',
#                 '-tr', '100', '100',	#target resolution <xres> <yres>
#                 '-r', 'mode',			#resampling method e.g. sum OR mode
#                 '-co', 'COMPRESS=LZW', '-co', 'NUM_THREADS=ALL_CPUS',	#creation options
#                 '-ot', 'UInt16',		#output data type
#                 '-overwrite',			#overwrite target dataset if already exists
#                 temp / 'rasterise_value_1m.tif', temp / 'mode_resample_100m.tif'])	#srcfile, dstfile

#logger.info('Mode resampling completed')

##--translate and set nodata to zero

logger.info('Translating raster')

subprocess.call(['gdal_translate',
                 '-tr', '100', '100',	#target resolution <xres> <yres>                
                 '-ot', 'UInt16',		#output data type    
                 '-a_nodata', '0',		#set nodata value             
                 temp / 'rasterise_zid_100m.tif', outputs / 'zone_identity_100m.asc'])	#srcfile, dstfile

logger.info('Translating completed')

##--


