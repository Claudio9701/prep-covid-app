import streamlit as st
import geopandas as gpd
import h3
import plotly.express as px

st.title('Plataforma de Reactivacion Economica Post-COVID')

# Read data
hexs = gpd.read_file('inputs/hexs_candidates/')
hexs.rename(columns={'population': 'population_2020', 'is_candida': 'is_candidate'}, inplace=True)

# Helper function
def get_hex_neighbours(hex_id):
    neighboards = h3.hex_range_distances(hex_id, 2)
    return list(set.union(*neighboards[1:]))

# Procedure function
def calc_candidates(hexs, n_candidates, radius, threshold):
    candidates = []
    hexs['buffer'] = hexs.geometry.buffer(radius) # meters
    target_hex = hexs.copy().sort_values(['Ai', 'population_2020'], ascending=[True, False])

    while (len(candidates) < n_candidates) and (target_hex.iloc[0]['Ai'] < threshold):
        #1. Sort available candidates
        target_hex = target_hex.sort_values(['Ai', 'population_2020'], ascending=[True, False])

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
    nbs_lists = candidates_df['hex'].apply(get_hex_neighbours).tolist()
    nbs = list(set([hex_id for sublist in nbs_lists for hex_id in sublist])) # flatten and drop duplicates
    nbs_df = hexs.query(f"hex in {nbs}")

    return candidates_df, nbs_df

# Sidebar widgets
n_candidates = st.sidebar.slider('# de zonas', 0, 50, 5)
radius = st.sidebar.slider('Cobertura minima de la zona', 0, 10000, 500)
threshold = st.sidebar.slider('Valor maximo de accesibilidad', hexs['Ai'].min(), hexs['Ai'].max(), 0.001, 0.5)

# Create plots
candidates_df, nbs_df = calc_candidates(hexs, n_candidates, radius, threshold)
candidates_plot = candidates_df.to_crs(epsg=4326)
nbs_plot = nbs_df.to_crs(epsg=4326)

fig = px.choropleth_mapbox(candidates_plot,
                           geojson=candidates_plot.geometry,
                           locations=candidates_plot.index,
                           color='population_2020',
                           color_continuous_scale='Viridis',
                           mapbox_style="carto-positron",
                           center={"lat": -12.0630149, "lon": -77.0296179},
                           zoom=9,
                           opacity=1)
fig.add_choroplethmapbox(geojson=nbs_plot.geometry.__geo_interface__,
                         locations=nbs_plot.index,
                         z=["1"]*nbs_plot.shape[0],
                         showscale=False,
                         showlegend=False)

st.plotly_chart(fig, use_container_width=True)
