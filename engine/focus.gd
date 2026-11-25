extends RefCounted
## FOCUS: the depth of field of the scene's camera. Every layer of the stage (the background, each hero, each set
## piece, each free thing) is drawn sharp or soft by how far it is from the plane the camera is focused on.
##
## The camera rules of the show (docs/shooting.md): the wow comes from the camera, and much of it is focus: a near
## face soft at the edge of the picture while the one behind talks sharp, the focus jumping between them on a cue.
##
## How deep a layer is: its SCALE s on the screen against the front edge of the ground (engine/space.gd): 1 at the
## front edge, less deeper in, more for a hero standing nearer than the front edge ("near" in scene.json). For a real
## lens the blur of a point is in proportion to |1/f - 1/d|, and d (its distance) goes as 1/s: so the blur is simply
## in proportion to |s - s_focus|. The background is a layer too, at "back" (default: deeper than the far line).
##
## scene.json:
##   "focus": { "on": "cow", "aperture": 1.0, "back": 0.4 }    turns it on; what is sharp at the start; how shallow
##                                       the depth of field is (0 = everything sharp); the background's depth scale
##   script:  { "focus": "cow", "time": 0.6 }       pull the focus onto a hero (it stays on it while it walks)
##            { "focus": 0.8, "time": 1.0 }         onto a depth scale (1 = the front edge)
##            { "focus": "back" }                   onto the background
##            { "aperture": 1.6, "time": 1.0 }      the depth of field grows shallower / deeper
##
## Drawing: a managed layer is moved into a SubViewport of its own (a CanvasGroup would not do: the parts of a puppet
## are ordered by z_index, and those escape a group). The viewport's picture is shown on a layer of the main tree that
## takes the old layer's place in the drawing order, through a shader that samples it over a disc of the blur
## radius. A soft layer is rendered smaller (size_2d_override stretches the stage into it), which pre-blurs it
## for free and keeps the disc's taps few. Works in the Compatibility renderer (the web export).

const SHADER := """
shader_type canvas_item;
uniform float radius = 0.0;      // in texels of the (possibly smaller) picture
void fragment() {
	if (radius < 0.6) {
		COLOR = texture(TEXTURE, UV);
	} else {
		vec4 c = vec4(0.0);
		for (int i = 0; i < 24; i++) {
			float r = sqrt((float(i) + 0.5) / 24.0);
			float a = float(i) * 2.39996;
			c += texture(TEXTURE, UV + vec2(cos(a), sin(a)) * r * radius * TEXTURE_PIXEL_SIZE);
		}
		COLOR = c / 24.0;
	}
}
"""

const BLUR := 40.0          # blur radius (picture px of a 1280 px tall picture) per 1.0 of depth scale apart
const MAX_BLUR := 36.0      # never more than this (a face is still a face)
const SHRINKS := [1.0, 1.5, 2.0, 3.0, 4.0, 6.0]   # how much smaller a soft layer is rendered (few sizes: no churn)

var on := false
var aperture := 1.0
var back := 0.4                      # the background's depth scale
var target: Variant = 1.0            # a hero id, "back", or a depth scale
var s_focus := 1.0                   # the depth scale in focus now
var _from_s := 1.0
var _t := 0.0
var _dur := 0.0
var _ap_from := 1.0
var _ap_to := 1.0
var _ap_t := 0.0
var _ap_dur := 0.0
var _host: Node
var _shown: Dictionary = {}          # CanvasLayer -> {"vp": SubViewport, "show": CanvasLayer, "rect": TextureRect}
var _shader: Shader


func setup(spec: Dictionary, far_scale: float, host: Node) -> void:
	var f: Variant = spec.get("focus", null)
	if not (f is Dictionary):
		return
	on = true
	_host = host
	aperture = float(f.get("aperture", 1.0))
	_ap_to = aperture
	back = float(f.get("back", minf(far_scale * 0.6, 0.5)))
	target = f.get("on", 1.0)
	_shader = Shader.new()
	_shader.code = SHADER


## Moves the layer into a viewport of its own and shows that viewport's picture in its place.
func manage(layer: CanvasLayer) -> void:
	if not on or _shown.has(layer):
		return
	var pic: Vector2i = _host.get_viewport().get_visible_rect().size
	var vp := SubViewport.new()
	vp.transparent_bg = true
	vp.size = pic
	vp.size_2d_override = pic
	vp.size_2d_override_stretch = true
	vp.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	vp.canvas_item_default_texture_filter = Viewport.DEFAULT_CANVAS_ITEM_TEXTURE_FILTER_LINEAR
	_host.add_child(vp)
	layer.reparent(vp, false)
	var show := CanvasLayer.new()
	show.layer = layer.layer
	_host.add_child(show)
	var rect := TextureRect.new()
	rect.texture = vp.get_texture()
	rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	rect.stretch_mode = TextureRect.STRETCH_SCALE
	rect.size = Vector2(pic)
	rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	rect.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR
	var m := ShaderMaterial.new()
	m.shader = _shader
	rect.material = m
	show.add_child(rect)
	_shown[layer] = {"vp": vp, "show": show, "rect": rect, "shrink": 1.0}


## A script line: { "focus": ..., "time": ... } and / or { "aperture": ..., "time": ... }
func command(line: Dictionary, now_s: float) -> void:
	var time: float = float(line.get("time", 0.5))
	if line.has("focus"):
		target = line["focus"]
		_from_s = now_s
		_t = 0.0
		_dur = maxf(time, 0.0)
	if line.has("aperture"):
		_ap_from = aperture
		_ap_to = float(line["aperture"])
		_ap_t = 0.0
		_ap_dur = maxf(time, 0.0)


## One step. `target_s`: the depth scale of what the focus is on now (the stage measures it: a hero moves).
## `layers`: [[CanvasLayer, its depth scale], ...]. `zoom_rel`: the camera's zoom against its widest.
func step(dt: float, target_s: float, layers: Array, zoom_rel: float) -> void:
	if not on:
		return
	_t += dt
	var k: float = 1.0 if _dur <= 0.0 else smoothstep(0.0, 1.0, minf(_t / _dur, 1.0))
	s_focus = lerpf(_from_s, target_s, k)
	_ap_t += dt
	aperture = _ap_to if _ap_dur <= 0.0 else lerpf(_ap_from, _ap_to, smoothstep(0.0, 1.0, minf(_ap_t / _ap_dur, 1.0)))
	var pic: Vector2i = _host.get_viewport().get_visible_rect().size
	var px: float = pic.y / 1280.0
	for pair: Array in layers:
		var layer: CanvasLayer = pair[0]
		var d: Variant = _shown.get(layer, null)
		if d == null:
			continue
		(d["show"] as CanvasLayer).layer = layer.layer
		var r: float = aperture * BLUR * absf(float(pair[1]) - s_focus) * sqrt(maxf(zoom_rel, 1.0))
		r = minf(r, MAX_BLUR) * px
		var shrink: float = 1.0
		for f: float in SHRINKS:
			if r >= 5.0 * f:
				shrink = f
		var vp: SubViewport = d["vp"]
		var want := Vector2i(maxi(int(pic.x / shrink), 8), maxi(int(pic.y / shrink), 8))
		if vp.size != want or vp.size_2d_override != pic:
			vp.size = want
			vp.size_2d_override = pic
			(d["rect"] as TextureRect).size = Vector2(pic)
		(((d["rect"] as TextureRect).material) as ShaderMaterial).set_shader_parameter("radius", r / shrink)
