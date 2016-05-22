import json
import netCDF4
import shutil
import urllib
import os
import datetime
import os.path

from dateutil.rrule import rrule, DAILY
from numpy import where

from ..models import VegetationMapByHRU, ProjectionInformation

from flask import current_app as app
from flask import session
from flask.ext.security import current_user

from client.model_client.client import ModelApiClient
from client.swagger_client.apis.default_api import DefaultApi

LEHMAN_CREEK_CELLSIZE = 100  # in meters; should be in netCDF, but it's not


def propagate_all_vegetation_changes(original_prms_params, veg_map_by_hru):
    """
    Given a vegetation_updates object and an original_parameters netcdf,
    propagate the updates through the original prms params netcdf and return
    an updated copy of the PRMS parameter netCDF

    Arguments:
        original_prms_params (netCDF4.Dataset): Base PRMS parameters for the
            watershed under investigation
        veg_map_by_hru (dict): Dictionary with structure
            {
                'bare_ground': [ (HRUs with bare_ground) ],
                'grasses': [ (HRUs with grasses) ],
                #  ... and so on with fields as given in app/models.py
            }

    Returns:
        (netCDF4.Dataset) netCDF Dataset with parameters updated according to
            the veg_map_by_hru
    """
    ret = original_prms_params
    return ret


def get_veg_map_by_hru(prms_params_file):
    """
    Create the vegetation map by HRU, which will also include the elevations
    in an array indexed by HRU.

    Arguments:
        prms_params (netCDF4.Dataset): PRMS parameters netCDF
    Returns:
        (VegetationMapByHRU): JSON representation of the vegetation and
            elevation by HRU
    """
    prms_params = netCDF4.Dataset(prms_params_file, 'r')
    # latitudes read from top to bottom
    upper_right_lat = prms_params.variables['lat'][:][0]
    lower_left_lat = prms_params.variables['lat'][:][-1]

    # longitudes get increasingly negative from right to left
    lower_left_lon = prms_params.variables['lon'][:][0]
    upper_right_lon = prms_params.variables['lon'][:][-1]

    ctv = prms_params.variables['cov_type'][:].flatten()

    projection_information = ProjectionInformation(
        ncol=prms_params.number_of_columns,
        nrow=prms_params.number_of_rows,
        xllcorner=lower_left_lon,
        yllcorner=lower_left_lat,
        xurcorner=upper_right_lon,
        yurcorner=upper_right_lat,
        cellsize=LEHMAN_CREEK_CELLSIZE
    )

    vegmap = VegetationMapByHRU(
        bare_ground=where(ctv == 0)[0].tolist(),
        grasses=where(ctv == 1)[0].tolist(),
        shrubs=where(ctv == 2)[0].tolist(),
        trees=where(ctv == 3)[0].tolist(),
        conifers=where(ctv == 4)[0].tolist(),

        projection_information=projection_information
    )

    # ret = json.loads(vegmap.to_json())
    # ret['elevation'] = prms_params.variables['hru_elev'][:].flatten().tolist()
    vegmap.elevation = prms_params.variables['hru_elev'][:].flatten().tolist()

    return vegmap


def model_run_name(auth_host=None, model_host=None):
    """
    the function is used to collect model run names
    """

    cl = ModelApiClient(api_key=session['api_token'],auth_host=auth_host, model_host=model_host)

    api = DefaultApi(api_client=cl)

    # record all the model runs
    model_run = api.search_modelruns().objects

    temp_list = [0] * len(model_run)

    for loop_count in range(len(temp_list)):
        temp_item = model_run[loop_count]
        # for current version, we only display finished model run
        if temp_item['progress_state'] == 'FINISHED':
            temp_list[loop_count] = {'id': temp_item['id']}

    return json.dumps(temp_list)


def find_user_folder():
    username = current_user.email
    # get the first part of username as part of the final file name
    username_part = username.split('.')[0]
    app_root = os.path.dirname(os.path.abspath(__file__))
    app_root = app_root + '/../static/user_data/' + username_part
    return app_root


def use_default_model_run():
    app_root = find_user_folder()

    if not os.path.exists(app_root):
        os.mkdir(app_root)

    default_data_folder = app_root + '/../../data/'

    data_file = app_root + app.config['TEMP_DATA']
    control_file = app_root + app.config['TEMP_CONTROL']
    param_file = app_root + app.config['TEMP_PARAM']
    # copy the default file
    shutil.copyfile(default_data_folder +
                    app.config['DEFAULT_CONTROL'], control_file)
    shutil.copyfile(default_data_folder +
                    app.config['DEFAULT_DATA'], data_file)
    shutil.copyfile(default_data_folder +
                    app.config['DEFAULT_PARAM'], param_file)


def download_prms_inputs(control_url, data_url, param_url):
    app_root = find_user_folder()

    if not os.path.exists(app_root):
        os.mkdir(app_root)

    # TODO clean the previous download input files
    data_file = app_root + app.config['TEMP_DATA']
    control_file = app_root + app.config['TEMP_CONTROL']
    param_file = app_root + app.config['TEMP_PARAM']

    # clean up previous download file
    if os.path.isfile(data_file):
        os.remove(data_file)

    if os.path.isfile(control_file):
        os.remove(control_file)
        
    if os.path.isfile(param_file):
        os.remove(param_file)
    

    # download three inputs file based on the urls
    urllib.urlretrieve(control_url, control_file)
    urllib.urlretrieve(data_url, data_file)
    urllib.urlretrieve(param_url, param_file)

    app.logger.debug(
        'User: ' + current_user.email + ' finished downloading three input files')



# lisa's function, grab temperature from data.nc
# Rui modified it a little bit to fit current version program
def add_values_into_json(input_data_nc):

    variableList = []

    fileHandle = netCDF4.Dataset(input_data_nc, 'r')
    
    # Extract number of time steps
    dimensions = [dimension for dimension in fileHandle.dimensions] 
    if 'time' in dimensions:
        numberOfTimeSteps = len(fileHandle.dimensions['time'])

    # extract tmax and tmin variables and append to a list
    variables = [variable for variable in fileHandle.variables]
    
    if 'tmin' in variables:
        variableList.append('tmin')
    if 'tmax' in variables:
        variableList.append('tmax')
        
    for index in range(len(variables)):
        if '_' in variables[index]:
            position = variables[index].find('_')
            if 'tmax' in variables[index][0:position] or 'tmin' in variables[index][0:position]:
                variableList.append(variables[index])

    valueList = []
    for index in range(len(variableList)):
        valueList.append([])

    for index in range(len(variableList)):
        valueList[index] = fileHandle.variables[variableList[index]][:].flatten().tolist()
    
    varValues = {}

    for index in range(len(variableList)):
        varValues[variableList[index]] = valueList[index]

    # Find time step values

    timeStepValues = []

    for variable in fileHandle.variables:
        if variable == 'time':
    
            units = str(fileHandle.variables[variable].units)
            startDate = units.rsplit(' ')[2]
            startYear = int(startDate.rsplit('-')[0].strip())
            startMonth = int(startDate.rsplit('-')[1].strip())
            startDay = int(startDate.rsplit('-')[2].strip())
            shape = str(fileHandle.variables[variable].shape)
            numberOfValues = int(shape.rsplit(',')[0].strip('('))
            endDate = str(datetime.date (startYear, startMonth, startDay) + datetime.timedelta (days = numberOfValues-1))
            endYear = int(endDate.rsplit('-')[0].strip())
            endMonth = int(endDate.rsplit('-')[1].strip())
            endDay = int(endDate.rsplit('-')[2].strip())

    startDate = datetime.date(startYear, startMonth, startDay)
    endDate = datetime.date(endYear, endMonth, endDay)

    for dt in rrule(DAILY, dtstart=startDate, until=endDate):
        #timeStepValues.append(dt.strftime("%Y %m %d 0 0 0"))
        timeStepValues.append(dt.strftime("%Y-%m-%dT00:00:00"))
    
    data = { 
              'temperature_values': varValues, \
              'timestep_values': timeStepValues \
           }
    
    fileHandle.close()

    return json.dumps(data)

def add_values_into_netcdf(original_nc, post_data, update_file):
    '''
    this function is bascially from Lisa, Rui changed it to fit the post request from
    the client side
    '''
    temperature = post_data.json['temperature_values']


    fileHandle = netCDF4.Dataset(original_nc, mode='a')

    for index in range(len(temperature.keys())):
        fileHandle.variables[temperature.keys()[index]][:] = \
        temperature[temperature.keys()[index]]

    shutil.move(original_nc, update_file)

    
    fileHandle.close()
