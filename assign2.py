import utility
import pandas as pd
import numpy as np
import itertools
import time
import collections
import networkx as nx

def main():
	
	sub_n = 200

	multi = utility.read_multi()
	G = multi.layers_as_subgraph(['taz', 'streets'])

	print 'converting to igraph format'
	g = utility.nx_2_igraph(G)
	
	print 'computing od_dict for ITA()'
	start = time.clock()
	od = od_dict(g, od_data_dir = '1. data/taz_od/', od_file_name = '0_1.txt')
	
	sub_keys = od.keys()[:sub_n]
	sub_od = {k : od[k] for k in sub_keys}
	
	print 'running ITA()'
	ITA(g, od)
	
	# grab the new congested times, write them to multi, and save to .txt
	print 'saving ITA() results to test.py'
	d = {(g.vs[g.es[i].source]['id'], g.vs[g.es[i].target]['id']) : g.es[i]['congested_time_m'] for i in range(len(g.es))}
	nx.set_edge_attributes(multi.G, 'congested_time_ITA_m', d)
	print 'ITA (igraph) completed in ' + str((time.clock() - start) / 60.0) + ' m'

	# start = time.clock()
	# print 'computing od_dict for geo_betweenness_ITA()'
	# od = od_dict(g, od_data_dir = '1. data/taz_od/', od_file_name = '0_1.txt', nx_keys = True)
	# sub_keys = od.keys()[:sub_n]
	# sub_od = {k : od[k] for k in sub_keys}

	# print 'running geo_betweenness_ITA()'
	# v, l = multi.geo_betweenness_ITA(volumeScale = .25, OD = sub_od)
	# print v
	# nx.set_edge_attributes(multi.G, 'congested_time_geo_m', v)
	# print 'geo_betweenness_ITA() completed in in ' + str((time.clock() - start) / 60.0) + ' m'
	
	multi.to_txt('2. multiplex', 'test')

def read_od(data_dir, file_name):
    print 'reading OD data'
    data_dir = data_dir
    file_name = file_name
    od = pd.read_table(data_dir + file_name, sep = " ")
    return od

def od_dict(g, od_data_dir, od_file_name, nx_keys = False):
    '''
    Figure out how much of this function generalizes to work for networkx keys as well,
    would be cool to use the same one for both igraph keys and for Zeyad's networkx keys. 
    ''' 
    start = time.clock()
    # compute 'base' of origin-destination pairs -- we lookup information onto the base
    taz_vs = g.vs.select(lambda v : v['layer'] == 'taz')
    taz_indices = [v.index for v in taz_vs]
    o = [p[0] for p in itertools.product(taz_indices, taz_indices)] 
    d = [p[1] for p in itertools.product(taz_indices, taz_indices)]
    df = pd.DataFrame({'o' : o, 'd' : d})
    
    # lookup the taz corresponding to the origin and the destination
    taz_lookup = {v.index : int(v['taz']) for v in taz_vs}
    df['o_taz'] = df['o'].map(taz_lookup.get) 
    df['d_taz'] = df['d'].map(taz_lookup.get)
    
    # add flow by taz
    od = read_od(data_dir = od_data_dir, file_name = od_file_name)
    od.rename(columns = {'o' : 'o_taz', 'd' : 'd_taz'}, inplace = True)
    df = df.merge(od, left_on = ['o_taz', 'd_taz'], right_on = ['o_taz', 'd_taz'])
    
    # compute normalizer
    taz_norms = df.groupby(['o_taz','d_taz']).size()
    taz_norms = pd.DataFrame(taz_norms)
    taz_norms.rename(columns = {0 : 'taz_norm'}, inplace = True)
    
    # merge normalizer into df and compute normed flows
    df = df.merge(taz_norms, left_on = ['o_taz', 'd_taz'], right_index = True)
    df['flow_norm'] = df['flow'] / df['taz_norm']

    if nx_keys:
    	key_lookup = {v.index : v['id'] for v in taz_vs}
    	df['o'] = df['o'].map(key_lookup.get)
    	df['d'] = df['d'].map(key_lookup.get)

    # Pivot -- makes for an easier dict comprehension
    od_matrix = df.pivot(index = 'o', columns = 'd', values = 'flow_norm')
    od_matrix[np.isnan(od_matrix)] = 0
    
    od = {i : {col : od_matrix[col][i] for col in od_matrix.columns if od_matrix[col][i] > 0.00001} for i in od_matrix.index}
    
    print 'OD dict computed in ' + str((time.clock() - start) / 60.0) + ' m'

    return od

def ITA(g, od, base_cost = 'cost_time_m', P = (0.4, 0.3, 0.2, 0.1), a = 0.15, b = 4., scale = .25, attrname = 'congested_time_m'):
    vs = g.vs
    es = g.es
    
    vs['flow'] = 0
    es['flow'] = 0
    es[attrname] = list(es[base_cost])
    
    edge_dict = collections.defaultdict(int)
    for p in P:
    	start = time.clock()
        print 'assigning for p = ' + str(p)
        for o in od:
            ds = od[o]
            if len(ds) > 0:
                targets = ds.keys()
                paths = g.get_shortest_paths(o, to=targets, weights=attrname, mode='OUT', output="vpath")
                for path in paths:
                    l = len(path)
                    if l > 0:
                        d = path[-1:][0]
                        flow = od[o][d]
                        for i in range(l):
                            vs[path[i]]['flow'] += p * scale * flow
                            if i < l - 1:
                                edge_dict[g.get_eid(path[i], path[i+1])] += p * scale * flow
        print 'assignment for p = ' + str(p) + ' completed in ' + str((time.clock() - start) / 60.0) + 'm'
        for key in edge_dict:
            es[key]['flow'] = edge_dict[key]
            es[key][attrname] = es[key][base_cost] * (1 + a*( es[key]['flow'] / float(es[key]['capacity']))**b)