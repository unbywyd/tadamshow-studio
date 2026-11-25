extends Node2D
const VideoHead := preload("res://video_head.gd")
## A recorded MOUTH (video) on a puppet's painted face: the hero stays painted whole, and where its mouth is drawn
## a soft oval shows a real mouth talking. (The other way, video_head.gd, replaces the whole head.)
##
## The clip is made by lab/mouth_clip.py: Ogg Theora, the left half the picture, the right half its mask (an oval).
## It is pinned to the eyes and the nose of the person, so in the clip the closed lips are always at MOUTH_U,
## MOUTH_V of the square and the jaw works under them.
##
## This node is a child of the head part's node: it turns and moves with the head. It goes where the rig says the
## hero's mouth is painted (parts.head.mouth: centre and size, made by tools/gen_mouth.py) and is drawn so that the
## real lips are MOUTH_GROW times as wide as the painted mouth: a mouth too big for the face is the joke.

const MOUTH_U := 0.5           # the closed lips in the clip's square (lab/mouth_clip.py)
const MOUTH_V := 0.37
const LIPS_W := 0.59           # the lips' width at rest, share of the square's side
const MOUTH_GROW := 1.7        # the real lips against the painted mouth's width
const FACE_FILL := 0.92        # ...but the oval never wider than this share of the painted face
const SIDE_WIDTH := 0.62       # in profile the same oval, this much narrower (a mouth seen from the side)

const SHADER := """
shader_type canvas_item;
void fragment() {
	vec2 uv = vec2(UV.x * 0.5, UV.y);
	vec3 c = texture(TEXTURE, uv).rgb;
	float a = smoothstep(0.05, 0.95, texture(TEXTURE, uv + vec2(0.5, 0.0)).g);
	COLOR = vec4(c, a);
}
"""

var player: VideoStreamPlayer
var cover: Node2D = null       # "lips" clips: the hero's own skin painted over its painted mouth, under the live lips
var rect := Rect2()
var lips_width := 0.0          # as drawn, puppet px (for a report)

static var _shader: Shader


## Puts the clip on `part` (a Puppet.Part, the head). `mouth` and `face` are the rig's parts.head.mouth and .face
## (sheet coords; either may be missing). `profile`: a side view. `reuse`: a player that already plays this clip
## (the hero turned: the clip goes on).
static func wear(part: Object, stream_path: String, host: Node, sound: bool, mouth: Dictionary, face: Dictionary,
		profile := false, reuse: VideoStreamPlayer = null) -> Node2D:
	var me: Node2D = load("res://video_mouth.gd").new()
	if _shader == null:
		_shader = Shader.new()
		_shader.code = SHADER
	var mat := ShaderMaterial.new()
	mat.shader = _shader
	me.material = mat
	# where the painted mouth is, in the head part's own frame (the part's joint is its origin)
	var painted: Rect2 = part.painted
	var c: Vector2 = painted.get_center() + Vector2(0.0, 0.22 * painted.size.y)
	var w: float = 0.26 * painted.size.x
	if not mouth.is_empty():
		c = Vector2(mouth["center"][0], mouth["center"][1]) - part.pivot
		w = float(mouth["size"][0])
	var face_w: float = float(face["size"][0]) if not face.is_empty() else painted.size.x * 0.7
	var q: float = minf(MOUTH_GROW * w / LIPS_W, FACE_FILL * face_w / 0.9)
	var qx: float = q * (SIDE_WIDTH if profile else 1.0)
	me.rect = Rect2(c.x - MOUTH_U * qx, c.y - MOUTH_V * q, qx, q)
	me.lips_width = LIPS_W * qx
	me.z_index = part.z + 2
	# A clip of the LIPS alone (lab/mouth_clip.py --shape lips, said in the .json beside it): the hero's painted mouth
	# would show round them, so it is painted over first with the hero's own skin (the colour round that mouth).
	var info: Variant = JSON.parse_string(FileAccess.get_file_as_string(stream_path.get_basename() + ".json")) 			if FileAccess.file_exists(stream_path.get_basename() + ".json") else null
	if info is Dictionary and info.get("shape", "oval") == "lips":
		var half := Vector2(0.8 * w, 0.85 * float(mouth["size"][1]) if not mouth.is_empty() else 0.55 * w)
		var patch := Polygon2D.new()
		var ring := PackedVector2Array()
		for i in 28:
			ring.append(c + Vector2(cos(TAU * i / 28.0) * half.x, sin(TAU * i / 28.0) * half.y))
		patch.polygon = ring
		patch.color = _skin_round(part, c, half)
		patch.z_index = part.z + 1
		part.node.add_child(patch)
		me.cover = patch
	if reuse != null and is_instance_valid(reuse):
		me.player = reuse
	else:
		var stream := VideoStreamTheora.new()
		stream.file = stream_path
		me.player = VideoStreamPlayer.new()
		if AudioServer.get_bus_index("Voice") >= 0:
			me.player.bus = "Voice"                 # (the music ducks under this bus: engine/sound.gd)
		me.player.stream = stream
		me.player.loop = VideoHead.loop
		me.player.volume_db = 0.0 if sound else -80.0
		me.player.position = Vector2(-4000, -4000)     # it only decodes; the picture is drawn by this node
		me.player.size = Vector2(8, 8)
		host.add_child(me.player)
		me.player.play()
	part.node.add_child(me)
	return me


## The hero's skin round its painted mouth: the middle colour of the head's picture in an arc just outside it.
static func _skin_round(part: Object, c: Vector2, half: Vector2) -> Color:
	var tex: Texture2D = part.skins[""]["texture"]
	var img: Image = tex.get_image()
	var origin: Vector2 = part.skins[""]["position"]          # the picture's corner in the part's frame
	var rs: Array = []
	var gs: Array = []
	var bs: Array = []
	# (above the mouth and beside it only: under it there may be a beard, a scarf, the chin's shadow)
	for i in 40:
		var a: float = PI + PI * i / 39.0 + (0.25 if i % 2 == 0 else -0.25)        # the upper half, a little past level
		for k: float in [1.2, 1.4, 1.6]:
			var q: Vector2 = c + Vector2(cos(a) * half.x, sin(a) * half.y) * k - origin
			if q.x >= 0 and q.y >= 0 and q.x < img.get_width() and q.y < img.get_height():
				var col: Color = img.get_pixelv(Vector2i(q))
				if col.a > 0.9:
					rs.append(col.r)
					gs.append(col.g)
					bs.append(col.b)
	if rs.is_empty():
		return Color(0.9, 0.75, 0.62)
	rs.sort()
	gs.sort()
	bs.sort()
	return Color(rs[rs.size() / 2], gs[gs.size() / 2], bs[bs.size() / 2])


static func take_off(me: Node2D, keep_player := false) -> void:
	if me.cover != null and is_instance_valid(me.cover):
		me.cover.queue_free()
	if not keep_player and me.player != null:
		me.player.queue_free()
	me.queue_free()


func _process(_delta: float) -> void:
	VideoHead.hold_end(player)
	queue_redraw()


func _draw() -> void:
	var tex := player.get_video_texture() if player != null else null
	if tex != null and tex.get_width() > 1:
		draw_texture_rect(tex, rect, false)
