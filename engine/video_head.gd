extends Node2D
## A recorded head (video) worn on a puppet's head part.
##
## The clip is made by lab/head_clip.py: Ogg Theora, the left half is the head in colour, the right half its mask.
## Theora is the only video Godot plays by itself on every platform, and it has no transparency, so the mask is
## read from the right half in the shader below. The head is always in the same place of the clip:
## the chin at CHIN_V of its height, the face (forehead to chin) FACE_H of its height.
##
## This node is a child of the head part's node, so it turns and moves with the head for free.

const CHIN_V := 0.882
const FACE_H := 0.588
const HEAD_H := 0.76          # hair top to chin, share of the clip's height (a typical head)
const HEAD_W := 0.45          # ears included, share of the clip's width
const HAT_WIDE := 1.25         # a hat is this much wider than the head
const HAT_DOWN := 0.27         # ... and its lower edge is this share of the head's height below the top of the head
const HAT_SHAPE := 1.32        # width / height of a plain cap; a hat wider than that has a brim and is worn wider
const HAT_WIDE_MAX := 2.0
## A recorded face is the point of the show, so it is BIG: forehead to chin at least this share of the body
## (neck to sole), whatever head the puppet was painted with. A usual puppet gets a head about half its body tall.
const FACE_BODY := 0.40
## A worn piece (a scarf with a hole for the face) is blown up together with the face, but only this much. A hole
## that needs more is too small for a face: the piece is left out and the recorded head is shown whole.
const WEAR_GROW := 1.8
## The FACE-IN-A-BOARD look (scene "faces": "board"): the hero keeps its painted head whole (hat, horns, ears, hair:
## who it is), and only an OVAL of the recorded face shows in a hole cut in it (rig parts.head.board: centre and size
## in the head picture's px). The board grows with its face when the face would be too small, but only this much.
const BOARD_GROW := 1.6
const BOARD_FILL := 1.06       # forehead to chin against the oval's height (a little more: the edge cuts the brow; the user liked it)
const BOARD_BODY := 0.30       # the face at least this share of the body (smaller than a whole recorded head)

const SHADER := """
shader_type canvas_item;
uniform bool clipped = false;          // only draw inside the hole of the worn piece
uniform sampler2D hole;                // the hole: opaque where the face may show
uniform vec2 hole_pos;                 // where that picture lies, in this node's own coordinates
uniform vec2 hole_size;
uniform bool board = false;            // the FACE-IN-A-BOARD look: only an oval of the face, a hole in the painted head
uniform vec2 oval_c;                   // the oval, in this node's own coordinates
uniform vec2 oval_r;
uniform vec3 hole_dark = vec3(0.09, 0.07, 0.06);
varying vec2 at;
void vertex() {
	at = VERTEX;
}
void fragment() {
	vec2 uv = vec2(UV.x * 0.5, UV.y);
	vec3 c = texture(TEXTURE, uv).rgb;
	float a = smoothstep(0.1, 0.9, texture(TEXTURE, uv + vec2(0.5, 0.0)).g);
	float inside = 1.0;                    // where the hole lets the face show (the worn piece's / the board's hole)
	if (clipped) {
		vec2 h = (at - hole_pos) / hole_size;
		inside = (h.x < 0.0 || h.y < 0.0 || h.x > 1.0 || h.y > 1.0) ? 0.0 : texture(hole, h).a;
	}
	if (board) {
		// THE FACE IN A HOLE CUT IN A BOARD (the user, 23.11). The edge is a painted picture laid on top
		// (_edge(), tools/gen_ring.py): a fine dark line and the cut's wall in shadow. The face is cut by THAT
		// picture's own hole, grown a little so it slips under the dark edge: no gaps, whatever the hole's shape.
		// (Without an edge picture: a plain oval.) The face is clean: no vignette, only a touch darker at the cut.
		vec2 d = (at - oval_c) / oval_r;
		float e = length(d);
		float ed = fwidth(e);
		c = mix(c * 0.35, c, a);                                   // round the face (outside the mask): in shade
		// the board's upper edge casts a FAINT shadow just onto the face: where the face is outside the hole shifted
		// a little down, it is a little darker (the user: "тень буквально чуть-чуть")
		float sh = smoothstep(0.93, 1.03, length(d - vec2(0.02, 0.08)));
		c *= 1.0 - 0.30 * sh;
		c *= 1.0 - 0.28 * smoothstep(0.91, 1.0, e);              // (the user: "края темнее чуть") soft, all round
		// THE CUT: a narrow dark band right inside the edge (the wall of the hole in shade), a little wider at the top
		// where the light from above does not reach; crisp on its outer side, so it reads as a hole cut in a board
		float top = clamp(-d.y, 0.0, 1.0);
		float w = 0.035 + 0.035 * top;
		float wall = smoothstep(1.0 - w - ed, 1.0 - w + ed * 2.0, e);
		c = mix(c, c * 0.18, 0.85 * wall);
		a = clipped ? inside : 1.0 - smoothstep(1.0 - ed, 1.0 + ed, e);
	} else {
		a *= inside;
	}
	COLOR = vec4(c, a);
}
"""

var player: VideoStreamPlayer
var rect := Rect2()
var face_height := 0.0        # forehead to chin as drawn, in the puppet's px
var note := ""                # what had to be decided about this head, for the report

static var _shader: Shader
static var _edge_cache: Dictionary = {}
const USE_EDGE := false
const EDGE := "res://media/rings/edge_wood"      # .png + .json (the inner hole's centre and radii)


## The painted edge of the face hole, read once: {texture, center, radius} or {} when there is none.
static func _edge() -> Dictionary:
	if _edge_cache.is_empty():
		var png := ProjectSettings.globalize_path(EDGE + ".png")
		var meta := ProjectSettings.globalize_path(EDGE.replace("edge_", "ring_") + ".json")
		var img := Image.load_from_file(png) if FileAccess.file_exists(png) else null
		var info: Variant = JSON.parse_string(FileAccess.get_file_as_string(meta)) if FileAccess.file_exists(meta) else null
		if img == null or not (info is Dictionary):
			_edge_cache = {"none": true}
		else:
			img.generate_mipmaps()
			_edge_cache = {"texture": ImageTexture.create_from_image(img), "center": info["center"], "radius": info["radius"]}
			var hp := ProjectSettings.globalize_path(EDGE.replace("edge_", "hole_") + ".png")
			if FileAccess.file_exists(hp):
				_edge_cache["hole"] = ImageTexture.create_from_image(Image.load_from_file(hp))
	return {} if _edge_cache.has("none") else _edge_cache
## false (scene "clip_loop": false): a clip plays once and its face stays on the last frame (a shot longer than
## its take must not jump back to the take's first frame and first word)
static var loop := true
const HOLD_BEFORE_END := 0.12   # seconds before a once-played clip's end it is paused on its frame (> 2 clip frames)


## Puts the clip on `part` (a Puppet.Part, the head). `neck_r` is the radius of the neck joint (puppet px).
## `face` is the rig's parts.head.face (the hole of the worn piece, sheet coords) or {}.
##
## A head with a HAT of its own (part.hat) shows the whole recorded head with only that hat on top of it.
## A head that has something to WEAR (a scarf, a hood: part.wear) keeps it: the recorded face goes into its hole,
## the shadow of the hole behind it, the worn piece on top. A head with nothing to wear is hidden whole and the
## recorded head sits straight on the body, its chin a little over the collar.
## `body` is the puppet's height, neck to sole (rig.body_height): the face is sized against it (FACE_BODY).
## Returns the node; free it with take_off().
## `reuse`: a player already playing this clip (a hero turning round): the picture moves, the sound goes on.
static func wear(part: Object, neck_r: float, stream_path: String, host: Node, sound: bool, face: Dictionary = {},
		body: float = 0.0, reuse: VideoStreamPlayer = null, board: Dictionary = {}) -> Node2D:
	var me = load("res://video_head.gd").new()
	me.name = "video_head"
	if _shader == null:
		_shader = Shader.new()
		_shader.code = SHADER
	var mat := ShaderMaterial.new()
	mat.shader = _shader
	me.material = mat
	me.z_index = part.z + 1
	me.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR
	var sprite: Sprite2D = part.sprite
	var q: float
	var need: float = FACE_BODY * body / FACE_H        # the clip must be drawn at least this big (puppet px)
	var grow := 1.0
	var worn: bool = part.hat == null and part.wear != null and not face.is_empty()
	if not board.is_empty():
		worn = false
		var c: Vector2 = part.skins[""]["position"] + Vector2(board["center"][0], board["center"][1])
		var r: Vector2 = Vector2(board["size"][0], board["size"][1]) * 0.5
		q = BOARD_FILL * 2.0 * r.y / FACE_H
		grow = clampf(BOARD_BODY * body / (FACE_H * q), 1.0, BOARD_GROW)
		part.node.scale = Vector2.ONE * grow            # the board and the face in it grow together, from the neck
		var chin_y: float = c.y + 0.92 * r.y
		me.rect = Rect2(c.x - q * 0.5, chin_y - CHIN_V * q, q, q)
		mat.set_shader_parameter("board", true)
		mat.set_shader_parameter("oval_c", c)
		mat.set_shader_parameter("oval_r", r)
		# the EDGE of the hole: a painted picture (tools/gen_ring.py), its inner hole laid exactly on the oval
		# (the user, 23.11, after trying painted edges, rims and emboss: none of it — only the hole and a faint
		# shadow from its upper edge; the edge picture stays switched off)
		var edge: Dictionary = _edge() if USE_EDGE else {}
		if not edge.is_empty():
			var e := Sprite2D.new()
			e.name = "worn"
			e.texture = edge["texture"]
			e.centered = false
			var k: Vector2 = r / Vector2(edge["radius"][0], edge["radius"][1])
			e.scale = k
			e.position = c - Vector2(edge["center"][0], edge["center"][1]) * k
			e.z_index = part.z + 2
			e.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
			part.node.add_child(e)
			me.set_meta("worn", e)
			if edge.has("hole"):          # the face is cut by the painted hole itself: no gaps at its edge
				mat.set_shader_parameter("clipped", true)
				mat.set_shader_parameter("hole", edge["hole"])
				mat.set_shader_parameter("hole_pos", e.position)
				mat.set_shader_parameter("hole_size", Vector2(edge["texture"].get_size()) * k)
	elif worn:
		# The face fills the hole: as tall as the hole from forehead to chin, never narrower than it, the chin just
		# inside its lower edge. What the scarf covers of the forehead and the ears is simply behind the scarf.
		# The whole face must show, forehead to chin: that sets the size. A hole wider than the face is not
		# filled by blowing the face up (the eyes would go under the top edge): the shadow inside shows at the sides.
		var tall: float = 0.94 * float(face["size"][1]) / FACE_H
		q = minf(maxf(tall, 0.9 * float(face["size"][0]) / HEAD_W), 1.12 * tall)
		grow = maxf(need / q, 1.0)
		if grow > WEAR_GROW:
			me.note = "the hole in the painted head is %.1f times too small for a face: the recorded head is shown whole" % grow
			worn = false
			grow = 1.0
	if worn:
		var c: Vector2 = Vector2(face["center"][0], face["center"][1]) - part.pivot
		var hole: Vector2 = Vector2(face["size"][0], face["size"][1])
		var chin_y: float = c.y + 0.46 * hole.y
		part.node.scale = Vector2.ONE * grow            # the scarf and the face in it grow together, from the neck
		me.rect = Rect2(c.x - q * 0.5, chin_y - CHIN_V * q, q, q)
		sprite.texture = part.back if part.back != null else null
		if part.back != null:            # the face shows only through the hole, never above or beside the scarf
			mat.set_shader_parameter("clipped", true)
			mat.set_shader_parameter("hole", part.back)
			mat.set_shader_parameter("hole_pos", part.skins[""]["position"])
			mat.set_shader_parameter("hole_size", part.back.get_size())
		for layer in [part.wear]:
			var top := Sprite2D.new()
			top.name = "worn"
			top.centered = false
			top.texture = layer
			top.position = part.skins[""]["position"]
			top.z_index = part.z + 2
			top.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
			part.node.add_child(top)
			me.set_meta("worn", top)
	elif board.is_empty():
		var painted: Rect2 = part.painted
		var chin_y: float = 0.3 * neck_r
		q = maxf(minf((chin_y - painted.position.y) / HEAD_H, 1.3 * painted.size.x / HEAD_W), need)
		me.rect = Rect2(-q * 0.5, chin_y - CHIN_V * q, q, q)
		sprite.visible = false
		if part.hat != null:
			# A hat: the recorded head is whole and the hat sits on its crown, a little wider than the head and
			# pulled down over the top of the hair.
			var top := Sprite2D.new()
			top.name = "worn"
			top.texture = part.hat
			# Where this head's top and sides really are is measured from the clip itself (tools/clip_info.py
			# writes <clip>.json); without it a usual head is assumed.
			var top_v: float = CHIN_V - HEAD_H
			var wide: float = HEAD_W
			var info: Variant = JSON.parse_string(FileAccess.get_file_as_string(stream_path.get_basename() + ".json")) 					if FileAccess.file_exists(stream_path.get_basename() + ".json") else null
			if info is Dictionary:
				top_v = float(info.get("top_v", top_v))
				wide = float(info.get("width", wide))
			var shape: float = float(part.hat.get_width()) / float(part.hat.get_height())
			var width: float = clampf(HAT_WIDE * shape / HAT_SHAPE, HAT_WIDE, HAT_WIDE_MAX) * wide * q
			top.scale = Vector2.ONE * (width / part.hat.get_width())
			top.offset = Vector2(0.0, -part.hat.get_height() * 0.5)          # the sprite's origin = the middle of its lower edge
			top.position = Vector2(0.0, me.rect.position.y + (top_v + HAT_DOWN * (CHIN_V - top_v)) * q)
			top.z_index = part.z + 2
			top.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
			part.node.add_child(top)
			me.set_meta("worn", top)

	me.face_height = FACE_H * q * grow
	if reuse != null:
		me.player = reuse
		part.node.add_child(me)
		return me
	var stream := VideoStreamTheora.new()
	stream.file = stream_path
	me.player = VideoStreamPlayer.new()
	if AudioServer.get_bus_index("Voice") >= 0:
		me.player.bus = "Voice"                 # (the music ducks under this bus: engine/sound.gd)
	me.player.stream = stream
	me.player.loop = loop
	me.player.volume_db = 0.0 if sound else -80.0
	me.player.position = Vector2(-4000, -4000)     # it only decodes; the picture is drawn by this node
	me.player.size = Vector2(8, 8)
	host.add_child(me.player)
	me.player.play()
	part.node.add_child(me)
	return me


## `keep_player`: the clip goes on playing (it is handed to the head of another view).
static func take_off(me, part: Object, keep_player := false) -> void:
	var sprite: Sprite2D = part.sprite
	part.node.scale = Vector2.ONE
	sprite.visible = true
	sprite.texture = part.skins[part.skin]["texture"]
	if me.has_meta("worn"):
		(me.get_meta("worn") as Node).queue_free()
	if not keep_player:
		me.player.queue_free()
	me.queue_free()


func _process(_delta: float) -> void:
	hold_end(player)
	queue_redraw()


## A clip that plays once (loop false) is PAUSED a little before its end: a paused player keeps showing its frame,
## while a player that reaches the end flashes the clip's first frame before it stops (the face "came back").
static func hold_end(p: VideoStreamPlayer) -> void:
	if loop or p == null or p.paused or not p.is_playing():
		return
	var n: float = p.get_stream_length()
	if n > 0.0 and p.stream_position >= n - HOLD_BEFORE_END:
		p.paused = true


func _draw() -> void:
	var tex := player.get_video_texture() if player != null else null
	if tex != null and tex.get_width() > 1:
		draw_texture_rect(tex, rect, false)
