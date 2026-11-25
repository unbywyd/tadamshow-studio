extends Node2D
## The pin drawn on a joint. By default a filled disc with a darker rim; with `texture` (the shared wooden PEG,
## engine/hands/peg.png, puppet.gd pin_style "peg") that picture, `radius` across half of it.

var radius := 7.0
var fill := Color("e9dcc0")
var rim := Color("4a3220")
var texture: Texture2D = null
var always := false      # part of the look (a knot): shown even when the pins are hidden


func _draw() -> void:
	if texture != null:
		draw_texture_rect(texture, Rect2(-Vector2.ONE * radius, Vector2.ONE * radius * 2.0), false)
		return
	draw_circle(Vector2.ZERO, radius, rim, true, -1.0, true)
	draw_circle(Vector2.ZERO, radius * 0.68, fill, true, -1.0, true)
