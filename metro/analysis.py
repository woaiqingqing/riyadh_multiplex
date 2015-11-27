from math import sqrt
from metro import utility
import networkx as nx
import numpy as np

def distance(pos1,pos2):
	"""Compute geographical distance between two points
	
	Args:
		pos1 (tuple): a tuple of the form (lat, lon)
		pos2 (tuple): a tuple of the form (lat, lon)
	
	Returns:
		float: the geographical distance between points, in kilometers
	"""
	LAT_DIST = 110766.95237186992 / 1000.0 # in km. See http://www.csgnetwork.com/degreelenllavcalc.html
	LON_DIST = 101274.42720366278 / 1000.0 # in km. See http://www.csgnetwork.com/degreelenllavcalc.html
	return sqrt((LON_DIST*(pos1[0]- pos2[0]))**2 + (LAT_DIST*(pos1[1] - pos2[1]))**2)

def gini_coeff(x):
	'''
	compute the gini coefficient from an array of floats
	
	From http://www.ellipsix.net/blog/2012/11/the-gini-coefficient-for-distribution-inequality.html
	
	Args:
		x (np.array()): an array of floats
	'''
	# requires all values in x to be zero or positive numbers,
	# otherwise results are undefined
	n = len(x)
	s = x.sum()
	r = np.argsort(np.argsort(-x)) # calculates zero-based ranks
	return 1 - (2.0 * (r*x).sum() + s)/(n*s)

def igraph_betweenness_centrality(self, layers = None, weight = None, attrname = 'bc'):
		'''
		compute the (weighted) betweenness centrality of one or more layers and save to self.G.node attributes. 
		args: 
			thru_layers -- the layers on which to calculate betweenness. 
			source_layers -- the layers to use as sources in betweenness calculation.
			target_layers -- the layers to use as targets in the betweenness calculation.  
		'''
		print 'Computing betweenness centrality -- this could take a while.' 

		g = utility.nx_2_igraph(self.layers_as_subgraph(layers))

		bc = g.betweenness(directed = True,
						  cutoff = 300,
						  weights = weight)
		print 'betweenness calculated'
		d = dict(zip(g.vs['name'], bc))
		d = {key:d[key] for key in d.keys()}

def local_intermodality(self, layer = None, thru_layer = None, weight = None):
	"""Compute the local intermodality of a set of nodes and save as a node attribute. 
	
	Args:
	    layer (str, optional): the layer for which to compute intermodality
	    thru_layer (str, optional): the layer through which a path couns as 'intermodal'
	    weight (str, optional): the numeric edge attribute used to weight paths
	
	Returns:
	    None
	"""
	g = utility.nx_2_igraph(self.G)
	nodes = g.vs.select(layer=layer)

	def intermodality(v, g, nodes = nodes, weight = weight):
		paths = g.get_shortest_paths(v, nodes, weights = weight)
		total = len(nodes)
		intermodal = 0
		for p in paths: 
			if thru_layer in [g.vs[u]['layer'] for u in p]:
				intermodal += 1
		return intermodal * 1.0 / total

	d = {v['name'] : intermodality(v = v, g = g, nodes = nodes, weight = weight) for v in nodes}
	
	nx.set_node_attributes(self.G, 'intermodality', d)

def spatial_outreach(multi, node_layer = 'taz', thru_layers = ['streets'], weight = None, cost = None, attrname = 'outreach'):
	'''
	Compute the spatial outreach of all nodes in a layer according to a specified edge weight (e.g. cost_time_m). 
	Currently uses area of convex hull to measure outreach.
	
	Args:
	    layer (TYPE, optional): the layer in which to compute spatial outreach
	    weight (TYPE, optional): the numeric edge attribute by which to measure path lengths
	    cost (TYPE, optional): the maximum path length 
	    attrname (str, optional): the base name to use when saving the computed outreach
	'''
	from shapely.geometry import MultiPoint
	
	def distance_matrix(nodes, weight):
		N = len(nodes)

		lengths = g.shortest_paths_dijkstra(weights = weight, source = nodes, target = nodes)
		d = {nodes[i] : {nodes[j] : lengths[i][j] for j in range(N) } for i in range(N)}
		return d

	def ego(n, cost, d):
		return [j for j in nodes if d[n][j] <= cost]

	def area(n, cost, d):
		points = [pos[n] for n in ego(n, cost, d)]
		return MultiPoint(points).convex_hull.area
		
	print 'converting to igraph'
	g = utility.nx_2_igraph(multi.layers_as_subgraph(thru_layers + [node_layer]))
	nodes = g.vs.select(lambda vertex: vertex['layer'] == node_layer)['name']
	pos = {v['name'] : (v['lon'], v['lat']) for v in g.vs.select(lambda v: v['name'] in nodes)}
	print 'computing distance matrix'
	d = distance_matrix(nodes, weight)
	print 'computing outreach'
	outreach = {n : sqrt(area(n, cost, d)) for n in nodes}
	nx.set_node_attributes(multi.G, attrname, outreach)

def proximity_to(multi, layers, to_layer):
	"""Calculate how close nodes in one layer are to nodes in another. Closeness 
	is measured as Euclidean distance, not graph distance. 
	
	Args:
	    layers (TYPE): base layer from which to compute proximity
	    to_layer (TYPE): layer to which to calculate proximity 
	
	Returns:
	    TYPE: Description
	"""
	layers_copy = multi.layers_as_subgraph(layers)	
	to_layer_copy = multi.layers_as_subgraph([to_layer])
	d = {n : utility.find_nearest(n, layers_copy, to_layer_copy)[1] for n in layers_copy.node}
	nx.set_node_attributes(multi.G, 'proximity_to_' + to_layer, d)

def accessible_nodes(self, origin, weight, limit):
        '''
        Returns a dictionary of all nodes that can be accessed within the given limit according to the specified weight
        
        Args:
    origin (str): the source node
    weight (str): the edge weight by which to compute shortest paths.
    limit (float): the upper bound for accessible shortest paths
                
Returns:
    dict: a dictionary of shortest path lengths (in the given weight) indexed by the destination node
        '''
        q = [ (0, origin, None) ]
        seen = {}
        while q:
            dist, current, parent = heappop(q)
            if dist > limit: break
            seen[current] = dist
            for nextNode, edge in self.G[current].items():
                if nextNode in seen: continue
                heappush(q, (dist + edge[weight], nextNode, current) )  
        return seen

def weighted_betweenness(g, od, weight = 'free_flow_time_m',scale = .25, attrname = 'weighted_betweenness'):
    vs = g.vs
    es = g.es
    
    # initialize graph attributes for collecting later
    vs[attrname] = 0
    
    # collects flows
    node_dict = collections.defaultdict(int)

    # main assignment loop
    start = time.clock()
    for o in od:
        ds = od[o]
        if len(ds) > 0:
            targets = ds.keys()
            paths = g.get_shortest_paths(o, 
                                         to=targets, 
                                         weights=weight, 
                                         mode='OUT', 
                                         output="vpath") # compute paths
            for path in paths:
                if len(path) > 0:
                    flow = ds[path[-1:][0]]
                    for v in path: 
                        node_dict[v] += scale * flow
                    
    print 'betweenness calculated in in ' + str(round((time.clock() - start) / 60.0,1)) + 'm'
    for key in node_dict:
        vs[key][attrname] = node_dict[key]