import geopandas as gpd
from h3 import hex_range_distances
import pandas as pd
from functools import reduce
from shapely.ops import unary_union
from urbanpy.utils import geo_boundary_to_polygon

ind_labels = {'Densidad Poblacional': 'population_2020',
              'Densidad Poblacional (<5 años)': 'population_children',
              'Densidad Poblacional (15-24 años)': 'population_youth', 
              'Densidad Poblacional (>60 años)': 'population_elderly',
              'Accesso a Comercios aledaños': 'Ai',
              'Disponibilidad de Comercios aledaños': 'ds',
              'Lugares de Venta Minorista': 'Retail', 
              'Lugares de Servicios': 'Services',
              'Lugares de Bebidas, Comidas y Alojamiento': 'BFA',
              'Lugares de Manufactura': 'Manufacturing', 
              'Lugares de Otros': 'Other',
              'Ingreso Promedio por Hogar': 'INGR_HOG_PROM',
              'Ingreso Per Cápita en General': 'INGR_PER',
              'Ingreso Per Cápita Alto (>1700)': 'Alto', 
              'Ingreso Per Cápita Medio Alto (900-1700)': 'Medio Alto', 
              'Ingreso Per Cápita Medio (550-900)': 'Medio',
              'Ingreso Per Cápita Medio Bajo (380-550)': 'Medio Bajo', 
              'Ingreso Per Cápita Bajo (<550)': 'Medio Bajo',
              'Vulnerabilidad Monetaria': 'vulnerabilidad_monetaria',
              'Vulnerabilidad Laboral': 'vulnerabilidad_laboral',
              'Vulnerabilidad Hídrica': 'vulnerabilidad_hidrica',
              'Distancia al Lugar de Venta de Alimento más cercano': 'distance_to_food_facility',
              'Duranción del viaje al Lugar de Venta de Alimento más cercano': 'distance_to_food_facility',
              'Distancia al Centro de Salud más cercano': 'distance_to_health_facility',
              'Duranción del viaje al Centro de Salud más cercano': 'duration_to_health_facility',}

plotly_chart_labels = {v: k for k, v in ind_labels.items()}

sort_ascending = {'Ascendentemente': True, 'Descendentemente': False}

plotly_radar_labels = {'group':'Grupo', 'indicator_labels':'Indicador', 'value':'Valor'}

def create_ind_param(label, sort_asc):
    return {'col_name': ind_labels[label], 'ascending': sort_ascending[sort_asc]}

def get_hex_neighbours(hex_id, range_distance=2):
    neighboards = hex_range_distances(hex_id, range_distance)
    nbs_h3ids = list(set.union(*neighboards))
    nbs_geometries =  unary_union([geo_boundary_to_polygon(h3id) for h3id in nbs_h3ids])
    return nbs_h3ids, nbs_geometries

def get_zones(hexs, hex_col='hex', range_distance=2):
    '''
    Returns
    -------
    zones: regions represented by hexagon sets from the H3 geospatial indexing system.
    '''
    hexclusters = hexs.apply(lambda row: get_hex_neighbours(row[hex_col], range_distance),
                            axis=1, result_type='expand')
    hexclusters = hexclusters.reset_index()
    hexclusters.columns = ['zone_id', 'h3cluster', 'geometry']
    zones = gpd.GeoDataFrame(hexclusters, crs='epsg:4326')
    
    return zones

def filter_green_areas(green_areas, zones, hexs):
    green_areas_copy = green_areas.copy()
    green_areas_copy = green_areas_copy.reset_index()

    hexs_copy = hexs.copy()
    hexs_copy = hexs_copy.to_crs(epsg=4326)

    filtered_green_areas = (gpd.sjoin(green_areas_copy, zones) # Mask green areas with zones
    .drop_duplicates('index') # Remove duplicates (candidates that intersect with more than one zone)
    .drop(['index_right', 'h3cluster'], axis=1)) # Remove unused cols

    h3_ixs = [item for item_list in zones['h3cluster'] for item in item_list] # Flatten h3cluster ixs
    nbs_hexs = hexs_copy.query(f"hex in {h3_ixs}") # Filter hexs with indicators 

    filtered_green_areas = gpd.sjoin(filtered_green_areas, nbs_hexs) # Add indicators to candidates
    
    return filtered_green_areas

def sample_n_per_group(group, sample_sizes):
    return pd.DataFrame.sample(group, n=sample_sizes[group.name])

def sample_random_candidates(candidates, group_col, n):
    '''
    Random sample of size N for each zone
    
    Parameters
    ----------
    n: Size of sample for each zone
    '''
    ss = candidates[group_col].value_counts().clip(upper=n).to_dict() # Handle len(groups) < n

    candidate_groups = candidates.groupby('zone_id', group_keys=False)
    candidate_rsample = candidate_groups.apply(sample_n_per_group, sample_sizes=ss)
    
    return candidate_rsample

def calc_candidates(hexs_orig, n_candidates, radius, threshold, primary_ind, secondary_ind, green_areas):
    candidates = []
    hexs = hexs_orig.copy() # Freely mutate cached object
    hexs = hexs.to_crs(epsg=32718)
    hexs['buffer'] = hexs.geometry.buffer(radius) # meters
    target_hex = hexs.sort_values([primary_ind['col_name'], secondary_ind['col_name']], ascending=[primary_ind['ascending'], secondary_ind['ascending']])

    def eval_threshold(primary_ind=primary_ind, threshold=threshold):
        if primary_ind['ascending']:
            return target_hex.iloc[0][primary_ind['col_name']] < threshold
        else:
            return target_hex.iloc[0][primary_ind['col_name']] > threshold
         
    while (len(candidates) < n_candidates) and eval_threshold():
        #1. Sort available candidates
        target_hex = target_hex.sort_values([primary_ind['col_name'], secondary_ind['col_name']], ascending=[primary_ind['ascending'], secondary_ind['ascending']])

        #2. Add block id to candidates
        candidate_idx = target_hex.iloc[0]['hex']
        candidates.append(candidate_idx)

        #3. Get the neighborhood buffer to filter blocks (maybe replace with the res 9 hex id to eliminate a whole hex)
        filter_buffer = target_hex.iloc[0]['buffer']

        #4. Remove candidate from target set
        target_hex = target_hex[target_hex['hex'] != candidate_idx]

        #5. Filter the candidate set (exclude hex closest neighbours)
        target_hex = target_hex[~target_hex.geometry.intersects(filter_buffer)]

    candidates_df = hexs[hexs['hex'].isin(candidates)]

    zones_df = get_zones(candidates_df)

    filtered_green_areas = filter_green_areas(green_areas, zones_df, hexs)

    return zones_df, filtered_green_areas

def get_indicators(indicators, groups, total_candidates):
    ''' 
    Get groups average indicators
    '''
    dfs = []
    for group_name, group_df in groups.items():
        group_inds = group_df[indicators].mean()
        group_inds.name = group_name
        dfs.append(group_inds)
        
    inds = reduce(lambda left, right: pd.merge(left, right, right_index=True, left_index=True), 
                  dfs).T
    
    # Standarize variables w.t.r to the total candidates to compare in radar plot
    inds_norm = ( inds - total_candidates[indicators].mean() ) / total_candidates[indicators].std()
    
    inds = inds.stack().reset_index()
    inds.columns = ['group', 'indicator', 'value']
    
    inds['value_norm'] = inds_norm.stack().values
        
    inds['indicator_labels'] = inds['indicator'].replace(plotly_chart_labels)
    
    return inds