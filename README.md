# Blender2DExporter
A basic Blender script to render a 2D view of a mesh.

# Usage
* Ensure that your **.blend** file is saved. This is required so that the script can identify where to output its rendered images.
* Open the **Scripting** tab in Blender
* Open ***Blender2DExporter.py***
* Click "**Run Script**"

# Requirements
* A camera must be present in the scene
* Tested on **Blender 3.3.1**

# Overview
This script calculates the combined bounds of meshes in the scene and fits the first camera it finds in the scene to fit the extents of the meshes in the XY plane.

The script then builds a simple compositing graph to output render elements to files.

Finally, the script executes a **Cycles** render and opens the output directory containing the rendered images.

# Features 
* By default, only **diffuse**, **normals**, and **depth** are output. It should be simple to add other targets if they are supported by Blender's Cycles output.
* Depth outputs are normalised to the mesh bounds min/max Z values.
* An optional ***render.cfg*** can be added to the directory containing the **.blend** file. The supported options are:
    * ***xy_padding*** - Padding added to the bounds of the meshes when fitting the camera
    * ***z_padding*** - Padding added to the camera's height when fitting
    * ***resolution*** - Output resolution of the rendered images. Default: **512x512**
    * ***camera_height*** - How far above the scene should the camera be placed. Largely redundant.
    * ***brightness_boost*** - Increases the brightness of the diffuse output using Blender's **BrightnessContrast** node
    * ***contrast_boost*** - Increases the contrast of the diffuse output using Blender's **BrightnessContrast** node
    * ***split_meshes*** - When set to true, the script will render each mesh in the scene to a separate set of output textures, but using the combined mesh bounds. This is useful for scenarios such as games wanting to enable/disable parts of a mesh, as all elements are separate, but still positioned correctly around a common origin and extents.
    * ***shrink_resolution_when_fitting*** - The script will perform rectangular fitting when mesh bounds in one dimension are multiples of the other dimension (e.g. A mesh is twice as large in X as Y) in order to save texel space. By default the script will maintain the resolution of the larger axis and shrink the smaller. If this is set to **False** then the larger axis will be scaled up instead.
        * **Example**: A mesh has bounds such that its X axis is 2x the size of the Y axis and the default resolution is set to 512.
        * ***shrink_resolution_when_fitting*** = *True* - Output texture will be 512 x 256
        * ***shrink_resolution_when_fitting*** = *False* - Output texture will be 1024 x 512

    
# Misc
* Render settings are not maintained by the script, so any manual rendering configuration will be overwritten by the script.
* The script is intended for fairly pedestrian render outputs. I have not tested the script with any advanced Blender features.
* Likely full of bugs if you try to use it for anything exotic

