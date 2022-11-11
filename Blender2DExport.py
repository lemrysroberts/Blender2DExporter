import bpy
import os
import math
import mathutils
import configparser

#---------------------------------------------------------------------------------------------------------------
# Troubleshooting:
#
# * I want to render only one of the meshes in the scene, but when I switch off the other meshes, the camera position seems weird
#		- Make sure the other meshes are disabled for *Render*, not just visibility in the scene (the camera icon in the hierarchy)
#---------------------------------------------------------------------------------------------------------------

OUTPUT_DIRECTORY = 'render'

#---------------------------------------------------------------------------------------------------------------

# Mapping between Blender render-layer IDs and our desired file output names
# i.e. Left is a fixed Blender name, right is ours
render_layer_output_dict = {
	'Depth' : 'depth',
	'Normal' : 'normal',
	'DiffCol' : 'diffuse',
}

#---------------------------------------------------------------------------------------------------------------

def ShowMessageBox(message = "", title = "Message Box", icon = 'INFO'):
	def draw(self, context):
		self.layout.label(text=message)
	bpy.context.window_manager.popup_menu(draw, title = title, icon = icon)

#---------------------------------------------------------------------------------------------------------------

def next_power_of_2(x):
    return 1 if x == 0 else 2 ** math.ceil(math.log2(x))

#---------------------------------------------------------------------------------------------------------------

# Calculates the target resolution
# This will try and do simple fitting for meshes that have rectangular bounds 
# N.B. I am avoiding any more complicated fitting logic, as it is a massive faff.
#      I just don't want to piss away texel space for long, thin meshes
def calculate_desired_resolution(target_resolution, dimension, shrink_smaller_axis = True):

	# Calculate the x/y and y/x ratios of the mesh bounds	
	ratio_x = dimension.x / dimension.y
	ratio_y = dimension.y / dimension.x

	# Calculate how many multiples of 2.0 each axis is, relative to the other axis
	x_scale_multiplier = 1.0 + math.floor(ratio_x / 2.0)
	y_scale_multiplier = 1.0 + math.floor(ratio_y / 2.0)

	# Scale the requested resolution down by the multiplier values, ensuring that we
	# always stay at a power of 2 to keep textures sensible
	# N.B. This *shrinks* the smaller axis by default. 
	# 	   Pass in False for shrink_smaller_axis in order to instead *grow* the larger axis
	if shrink_smaller_axis:
		resolution_x = next_power_of_2(target_resolution / int(y_scale_multiplier))
		resolution_y = next_power_of_2(target_resolution / int(x_scale_multiplier))
	else:
		resolution_x = next_power_of_2(target_resolution * int(x_scale_multiplier))
		resolution_y = next_power_of_2(target_resolution * int(y_scale_multiplier))

	return resolution_x, resolution_y

#---------------------------------------------------------------------------------------------------------------

class RenderParameters:
	xy_padding = 0.0
	z_padding = 0.0
	resolution = 0
	camera_height = 0.0
	brightness_boost= 0.0
	contrast_boost= 0.0
	split_meshes = False						# Render each mesh individually, using the combined bounds of all meshes
	shrink_resolution_when_fitting = True	    # Whether rectangular fitting should increase resolution to fit a longer axis, or shrink the resolution of the smaller axis
	camera_min_distance = 0.0
	camera_max_distance = 0.0
	output_path = ""

def RenderScene():

	render_params = RenderParameters()

	# Build some paths for later
	directory_name = os.path.dirname(bpy.context.blend_data.filepath)
	config_path = os.path.join(directory_name, 'render.cfg')
	render_params.output_path = os.path.join(directory_name, OUTPUT_DIRECTORY )

	# Read config
	config = configparser.ConfigParser()
	config.read(config_path)

	render_params.xy_padding = float(config.get('DEFAULT', 'xy_padding', fallback = 0.1))
	render_params.z_padding = float(config.get('DEFAULT', 'z_padding', fallback = 0.0))
	render_params.resolution = int(config.get('DEFAULT', 'resolution', fallback = 512))
	render_params.camera_height = float(config.get('DEFAULT', 'camera_height', fallback = 100))
	render_params.brightness_boost = float(config.get('DEFAULT', 'brightness_boost', fallback = 0.0))
	render_params.contrast_boost = float(config.get('DEFAULT', 'contrast_boost', fallback = 0.0))
	render_params.split_meshes = config.getboolean('DEFAULT', 'split_meshes', fallback = False)
	render_params.shrink_resolution_when_fitting = config.getboolean('DEFAULT', 'shrink_resolution_when_fitting', fallback = True)
		
	# Cache a scene reference for ease
	scene = bpy.context.scene

	# Calculate the bounds of scene objects
	min_bounds, max_bounds = GetSceneBounds()
	dimension = max_bounds - min_bounds
	max_xy_dimension = max(dimension.x, dimension.y)
	center = min_bounds + (dimension/ 2.0)

	# Calculate the output resolution based on the requested resolution and the mesh dimensions
	resolution = calculate_desired_resolution(render_params.resolution, dimension, render_params.shrink_resolution_when_fitting)

	# Output resolution
	scene.render.resolution_x = resolution[0]
	scene.render.resolution_y = resolution[1]

	# Calculate the max/min bounds distance from the camera for use when remapping the depth texture later
	render_params.camera_max_distance = render_params.camera_height - min_bounds.z + render_params.z_padding
	render_params.camera_min_distance = render_params.camera_height - max_bounds.z - render_params.z_padding

	# Position the camera
	cameraObject = bpy.data.objects['Camera']
	cameraObject.location.x = center.x
	cameraObject.location.y = center.y
	cameraObject.location.z = render_params.camera_height

	# Face the camera down the Z axis
	cameraObject.rotation_mode = 'XYZ'
	cameraObject.rotation_euler[0] = 0.0
	cameraObject.rotation_euler[1] = 0.0
	cameraObject.rotation_euler[2] = 0.0

	# Set the camera to orthographic and size it according to the content bounds
	bpy.data.cameras[0].type = 'ORTHO'
	bpy.data.cameras[0].ortho_scale = max_xy_dimension * (1.0 + render_params.xy_padding)

	# Set the camera far clip to accomodate objects centered around zero.
	# i.e. We position the camera at Z 100, so we want a clip-end greater than 100 to capture elements
	# below the Z zero line
	bpy.data.cameras[0].clip_end  = 1000

	# Set up render passes
	for view_layer in scene.view_layers:
		view_layer.use_pass_diffuse_color = True
		view_layer.use_pass_normal = True
		view_layer.use_pass_z = True
		view_layer.use_pass_ambient_occlusion = True

	# Set up the render engine
	scene.render.engine = 'CYCLES'          # Set the render-engine to Cycles for all the lovely high-quality render layers
	scene.render.use_file_extension = True  # Write file extensions
	scene.render.use_overwrite = True       # Always overwrite existing files
	scene.render.use_compositing = True     # Enable compositing or our graph won't get executed
	scene.render.film_transparent = True    # Enable transparent backgrounds so diffuse is alpha-ed correctly

	# split_meshes allows the renderer to output a single file per-mesh, while retaining the 
	# camera position and bounds for the combined mesh. 
	# This is useful for assembling multi-part meshes that don't require hand-fitting back together in Unity
	# It does however require that meshes are individually hidden/shown, and requires a mesh prefix to be added to filenames.
	# This means we pass a render_prefix string all over the place (empty string if split_meshes is False)
	if render_params.split_meshes:
		# Hide all meshes initially
		for scene_object in bpy.data.objects:
			if scene_object.type == 'MESH':
				scene_object.hide_render  = True

		# - Iterate all meshes
		# - Set them visible to rendering
		# - Create a prefix ID with the mesh name, to identify the render output
		# - Render
		# - Sanitize the rendered image filenames to get rid of Blender cruft
		# - Hide the mesh again
		for scene_object in bpy.data.objects:
			if scene_object.type == 'MESH':
				scene_object.hide_render = False
				render_prefix = scene_object.name + "_"
				render(render_prefix, render_params)
				bpy.ops.render.render()
				SanitizeFilenames(render_params.output_path, render_prefix)
				scene_object.hide_render = True

		# Set all meshes visible again
		for scene_object in bpy.data.objects:
			if scene_object.type == 'MESH':
				scene_object.hide_render = False
	else:
		# Non-split mesh (most commonly used). Just render all meshes in one pass, with no prefix
		render("", render_params)
		SanitizeFilenames(render_params.output_path, "")

	# Open an explorer window to the renders
	folder_to_open = render_params.output_path
	folder_to_open = os.path.realpath(folder_to_open)
	os.startfile(folder_to_open)

#---------------------------------------------------------------------------------------------------------------

def render(render_prefix, render_params):
	scene = bpy.context.scene

	# Set up the compositing node-tree
	scene.use_nodes = True
	tree = scene.node_tree

	# Remove all existing nodes
	for node in tree.nodes:
		tree.nodes.remove(node)
		
	# Create the render-layer input node
	render_layer_node = bpy.types.CompositorNodeRLayers(tree.nodes.new(type='CompositorNodeRLayers'))
	render_layer_node.location = -100, 0

	# Create a file-output node to write the render outputs to disk
	output_node = bpy.types.CompositorNodeOutputFile(tree.nodes.new(type = 'CompositorNodeOutputFile'))
	output_node.location = 1300, 0
	output_node.label = 'Outputs'
	output_node.base_path = render_params.output_path 
	output_node.format.color_depth = '16'

	# Clear the file-output slots
	output_node.layer_slots.clear()

	# Add a new slot for each file-output type and link it to the relevant render-layer node
	for input, output in render_layer_output_dict.items():
		file_input = output_node.layer_slots.new(render_prefix + output)
		tree.links.new(render_layer_node.outputs[input], file_input)

	# Add a node to remap the z range of the depth target
	depth_remap_node = bpy.types.CompositorNodeMapRange(tree.nodes.new(type = 'CompositorNodeMapRange'))
	depth_remap_node.location = 600, 130 
	depth_remap_node.inputs[1].default_value = render_params.camera_min_distance
	depth_remap_node.inputs[2].default_value = render_params.camera_max_distance
	depth_remap_node.inputs[3].default_value = 0.0
	depth_remap_node.inputs[4].default_value = 1.0
	tree.links.new(render_layer_node.outputs['Depth'], depth_remap_node.inputs[0])
	
	# Invert depth
	depth_invert_node = bpy.types.CompositorNodeMath(tree.nodes.new(type = 'CompositorNodeMath'))
	depth_invert_node.location = 800, 130 
	depth_invert_node.operation = 'SUBTRACT'
	depth_invert_node.inputs[0].default_value = 1.0

	tree.links.new(depth_remap_node.outputs[0], depth_invert_node.inputs[1])
	tree.links.new(depth_invert_node.outputs[0], output_node.inputs[render_prefix + 'depth'])

	# Add a node to handle any brightness increase
	brightness_node = bpy.types.CompositorNodeBrightContrast(tree.nodes.new(type = 'CompositorNodeBrightContrast'))
	brightness_node.location = 250, -200 
	brightness_node.inputs[1].default_value = render_params.brightness_boost
	brightness_node.inputs[2].default_value = render_params.contrast_boost
	tree.links.new(render_layer_node.outputs['DiffCol'], brightness_node.inputs[0])

	# Add a node to composite AO on to the diffuse color target
	ao_mix_node = bpy.types.CompositorNodeMixRGB(tree.nodes.new(type = 'CompositorNodeMixRGB'))
	ao_mix_node.location = 550, -200 
	ao_mix_node.blend_type = 'MULTIPLY'
	tree.links.new(brightness_node.outputs[0], ao_mix_node.inputs[1])
	tree.links.new(render_layer_node.outputs['AO'], ao_mix_node.inputs[2])

	# Add a node to apply the alpha mask to the diffuse
	set_alpha_node = bpy.types.CompositorNodeSetAlpha(tree.nodes.new(type = 'CompositorNodeSetAlpha'))
	set_alpha_node.location = 800, -120 

	tree.links.new(ao_mix_node.outputs[0], set_alpha_node.inputs[0])                # Link AO mix to the Set Alpha 
	tree.links.new(render_layer_node.outputs['Alpha'], set_alpha_node.inputs[1])    # Link the alpha render layer to Set Alpha
	tree.links.new(set_alpha_node.outputs[0], output_node.inputs[render_prefix + 'diffuse'])        # Link set Alpha to the output diffuse color

	# Add nodes to remap normal from[-1.0, 1.0] to [0.0, 1.0] and adjust gamma to have linear normals
	normal_add_node = bpy.types.CompositorNodeMixRGB(tree.nodes.new(type = 'CompositorNodeMixRGB'))
	normal_add_node.location = 350, -400 
	normal_add_node.blend_type = 'ADD'
	normal_add_node.inputs[2].default_value = (1.0, 1.0, 1.0, 1.0)
	tree.links.new(render_layer_node.outputs['Normal'], normal_add_node.inputs[1])

	normal_multiply_node = bpy.types.CompositorNodeMixRGB(tree.nodes.new(type = 'CompositorNodeMixRGB'))
	normal_multiply_node.location = 550, -400 
	normal_multiply_node.blend_type = 'MULTIPLY'
	normal_multiply_node.inputs[2].default_value = (0.5, 0.5, 0.5, 0.5)
	tree.links.new(normal_add_node.outputs[0], normal_multiply_node.inputs[1])

	normal_gamma_node = bpy.types.CompositorNodeGamma(tree.nodes.new(type = 'CompositorNodeGamma'))
	normal_gamma_node.location = 750, -400 
	normal_gamma_node.inputs[1].default_value = 2.2

	tree.links.new(normal_multiply_node.outputs[0], normal_gamma_node.inputs[0])
	tree.links.new(normal_gamma_node.outputs[0], output_node.inputs[render_prefix + 'normal'])

	# Render
	bpy.ops.render.render()

#---------------------------------------------------------------------------------------------------------------

def SanitizeFilenames(render_directory, render_prefix):
	filename =   os.path.splitext(bpy.path.basename(bpy.context.blend_data.filepath))[0] 
	files = os.listdir(render_directory)

	# Iterate over created textures removing the annoying 0001/0000 frame suffixes Blender adds
	# Also prepends the textures with the Blender filename
	for _, output in render_layer_output_dict.items():
		for file in files:
			if file.startswith(render_prefix + output):
				old_path = os.path.join(render_directory, file)
				new_path = os.path.join(render_directory, render_prefix + filename + '_' + output + '.png')
				os.replace(old_path, new_path)

#---------------------------------------------------------------------------------------------------------------

def GetSceneBounds():
	MAX_BOUND = 100000.0

	min_bounds = mathutils.Vector((MAX_BOUND, MAX_BOUND, MAX_BOUND))
	max_bounds = mathutils.Vector((-MAX_BOUND, -MAX_BOUND, -MAX_BOUND))
	
	# Iterate all visible scene meshes and adjust the min/max accordingly
	for scene_object in bpy.data.objects:
		if scene_object.type == 'MESH' and scene_object.visible_get():
			bbox_corners = [scene_object.matrix_world @ mathutils.Vector(corner) for corner in scene_object.bound_box]
			
			for corner in bbox_corners:
				min_bounds.x = min(min_bounds.x, corner.x)
				min_bounds.y = min(min_bounds.y, corner.y)
				min_bounds.z = min(min_bounds.z, corner.z)
				max_bounds.x = max(max_bounds.x, corner.x)
				max_bounds.y = max(max_bounds.y, corner.y)
				max_bounds.z = max(max_bounds.z, corner.z)
	
	return min_bounds, max_bounds
				
#---------------------------------------------------------------------------------------------------------------

if not bpy.data.is_saved:
	ShowMessageBox('Scene must be saved', 'Render Failed', 'ERROR')    
else:
	RenderScene()

#---------------------------------------------------------------------------------------------------------------