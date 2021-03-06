import streamlit as st
import geopandas as gpd
import plotly.express as px
from math import sqrt
from helpers import *

print()
print('-'*30)

st.set_page_config(
    page_title="PREP COVID-19",
    page_icon="😷",
    layout="centered",
    initial_sidebar_state="expanded",
)

st.title('Plataforma de Reactivación Económica Post-COVID-19')

# Read data
def read_gpd(file):
    return gpd.read_file(file)

hexs = read_gpd('inputs/lima_hexs9_complete.geojson')
candidate_green_areas = read_gpd('inputs/candidate_green_areas.geojson')
lima_distritos = read_gpd('inputs/lima_distritos.geojson')

# Sidebar widgets
st.sidebar.markdown('# Parámetros de las Zonas')

# Filtra el distrito WORK IN PROGRESS
district_opts = ['Todos'] + sorted(lima_distritos['distrito'].unique().tolist())
district = st.sidebar.selectbox('Selecciona el distrito que deseas ver', district_opts)

# Filter datasets within selected district
if district == 'Todos':
    selected_district = lima_distritos
    selected_hexs = hexs
    selected_green_areas = candidate_green_areas
    zoom_level = 9
    hexring_range_dist = 2
    radius_max = 10000
    radius_step = 100
    lat = -12.0630149
    lon = -77.0296179
else:
    selected_district = lima_distritos.query(f"distrito == '{district}'")
    selected_hexs = gpd.clip(hexs, selected_district)
    selected_green_areas = gpd.clip(candidate_green_areas, selected_district)
    # WARNING: There could be no green areas within the selected district
    zoom_level = 12
    selected_district_poly = selected_district.to_crs(epsg=32718).geometry.iloc[0]
    hexring_range_dist = calc_range_distances(selected_district_poly)
    radius_max = int(sqrt(selected_district_poly.area) * 0.10)
    radius_step = int(radius_max / 20)
    lat = selected_district.lat.iloc[0]
    lon = selected_district.lon.iloc[0]
print('hexs shape:', selected_hexs.shape)
print('green areas shape:', selected_green_areas.shape)

n_candidates = st.sidebar.slider('Cantidad de zonas a seleccionar', 0, 50, 5)
radius = st.sidebar.slider('Cobertura mínima de cada zona (en metros)', 0, radius_max, radius_step*2, radius_step)

st.sidebar.markdown('---') # separator

prim_ind = st.sidebar.selectbox('Selecciona el indicador principal', list(ind_labels.keys()), index=12) # preselect ingr_per, Ai 4
prim_ind_sort = st.sidebar.radio('¿Cómo quieres ordenarlo?', ('Ascendentemente', 'Descendentemente'), index=1, key='primary_ind_sort') # preselect ascending=False, True

threshold_min = selected_hexs[ind_labels[prim_ind]].min()
threshold_max = selected_hexs[ind_labels[prim_ind]].max()
threshold_value = selected_hexs[ind_labels[prim_ind]].median()

if threshold_min >= threshold_max:
    # Handle boleean vars
    threshold = 0
    # prim_ind_sort = 'Descendentemente' # TODO: Find a better way to handle this
else:
    if sort_ascending[prim_ind_sort]:
        threshold_type = 'máximo'
    else:
        threshold_type = 'mínimo'
    threshold = st.sidebar.slider(f'Valor {threshold_type} de {prim_ind}',
                                  threshold_min, threshold_max,
                                  float(threshold_value))

st.sidebar.markdown('---') # separator

# TODO: Delete active primary indicator from this second indicator selectbox
second_ind = st.sidebar.selectbox('Selecciona el indicador secundario', list(ind_labels.keys())) # preselect population_2020
second_ind_sort = st.sidebar.radio('¿Cómo quieres ordenarlo?', ('Ascendentemente', 'Descendentemente'), index=1, key='second_ind_sort')  # preselect ascending=False

# Data processing
primary_ind = create_ind_param(prim_ind, prim_ind_sort)
secondary_ind = create_ind_param(second_ind, second_ind_sort)

zones_df, filtered_green_areas = calc_candidates(selected_hexs, n_candidates, radius, threshold,
                                                 primary_ind,
                                                 secondary_ind,
                                                 selected_green_areas,
                                                 hexring_range_dist)
indicators_ok = False
if filtered_green_areas.shape[0] > 0:
    n_per_zone = 10 # Could be choosen by the user

    rselected_green_areas = sample_random_candidates(filtered_green_areas, 'zone_id', n_per_zone) # random selection
    
    topN_green_areas = (filtered_green_areas.sort_values([primary_ind['col_name'], secondary_ind['col_name']], 
                            ascending=[primary_ind['ascending'], secondary_ind['ascending']])
                            .groupby('zone_id').head(n_per_zone)) # select top N green areas

    sel_inds = ['population_2020', 'Retail', 'Ai', 'INGR_PER', 'vulnerabilidad_hidrica'] # Could be choosen by the user
    groups = {f'Top {n_per_zone}': topN_green_areas,
            'Aleatorio': rselected_green_areas}

    try:
        inds = get_indicators(sel_inds, groups, filtered_green_areas)
        indicators_ok = True
    except ValueError:
        pass
        

# Create plots
st.subheader('Zonas de Interés Seleccionados')
fig = px.choropleth_mapbox(zones_df,
                           geojson=zones_df.geometry,
                           locations=zones_df.index,
                           color=["1"]*zones_df.shape[0],
                           opacity=0.25)

fig.add_choroplethmapbox(geojson=selected_district.geometry.__geo_interface__,
                         locations=selected_district.index,
                         name='Distritos',
                         customdata=selected_district['distrito'],
                         z=["1"]*candidate_green_areas.shape[0],
                         colorscale=[[0, 'rgba(255,255,255,0)'], [1,'rgba(255,255,255,0)']],
                         marker_line_width=2,
                         marker_line_color='rgba(0,0,0,0.2)',
                         hovertemplate='Distrito:%{customdata}',
                         hoverlabel_namelength = 0,
                         showscale=False,)

fig.add_choroplethmapbox(geojson=selected_green_areas.geometry.__geo_interface__,
                         locations=selected_green_areas.index,
                         name='Áreas Verdes',
                         customdata=selected_green_areas['NOMBRE'],
                         z=["1"]*selected_green_areas.shape[0],
                         colorscale='greens',
                         marker_line_color='rgba(0,255,0,0.2)',
                         hovertemplate='Nombre:%{customdata}',
                         hoverlabel_namelength = 0,
                         showscale=False,)

if indicators_ok:
    fig.add_choroplethmapbox(geojson=rselected_green_areas.geometry.__geo_interface__,
                             locations=rselected_green_areas.index,
                             customdata=rselected_green_areas['NOMBRE'],
                             z=["1"]*rselected_green_areas.shape[0],
                             colorscale='reds',
                             marker_line_color='rgba(255,0,0,0.2)',
                             hovertemplate='Nombre:%{customdata}',
                             hoverlabel_namelength = 0,
                             showscale=False,)

    fig.add_choroplethmapbox(geojson=topN_green_areas.geometry.__geo_interface__,
                             locations=topN_green_areas.index,
                             customdata=topN_green_areas['NOMBRE'],
                             z=["1"]*topN_green_areas.shape[0],
                             colorscale='blues',
                             marker_line_color='rgba(0,0,255,0.2)',
                             hovertemplate='Nombre:%{customdata}',
                             hoverlabel_namelength = 0,
                             showscale=False,)

fig.update_layout(mapbox_style="carto-positron", mapbox_zoom=zoom_level, 
                  mapbox_center = {"lat": lat, "lon": lon},
                  showlegend=False, margin={"r":0,"t":0,"l":0,"b":0})

st.plotly_chart(fig, use_container_width=True)

st.subheader('Comparación de Grupos de Espacios Públicos en las Zonas')
if filtered_green_areas.shape[0] > 0 and indicators_ok:
    radar_fig = px.line_polar(inds, r='value_norm', theta='indicator_labels', color='group', line_close=True,
                            hover_data={'value':':.2f', 'indicator':False, 'group':False, 'value_norm':False}, 
                            labels=plotly_radar_labels, color_discrete_sequence=['blue', 'red'],)
    radar_fig.update_layout(polar={'radialaxis': {'showticklabels': False}})

    st.plotly_chart(radar_fig, use_container_width=True) 
else:
    st.write('No tenemos registradas suficientes áreas verdes en estas zonas.')
    st.write('Intenta cambiar los parámetros en la barra lateral de la izquierda para hayar nuevas zonas.')
