"""Engine import notes: how to bring each kind of asset into common tools.

Short, practical steps for Godot 4, three.js, Unity, Unreal and Blender. They
are generated from the asset's type, maps and size, so an agent gets the exact
wiring (which map goes where, normal-map convention, scale) next to the
download links.
"""
from __future__ import annotations

import re

ENGINES = {
    'godot': 'Godot 4',
    'threejs': 'three.js',
    'unity': 'Unity',
    'unreal': 'Unreal Engine 5',
    'blender': 'Blender',
}
_ALIASES = {'godot4': 'godot', 'godot 4': 'godot', 'three': 'threejs', 'three.js': 'threejs', 'web': 'threejs',
            'ue': 'unreal', 'ue5': 'unreal', 'unreal engine': 'unreal'}


def engine_id(value: str | None) -> str | None:
    if not value:
        return None
    key = str(value).strip().lower()
    key = _ALIASES.get(key, key)
    return key if key in ENGINES else None


def _size_hint(asset: dict) -> str | None:
    size = (asset.get('attributes') or {}).get('real_size_m')
    if not size:
        return None
    w, h = size[0], size[1] if len(size) > 1 else size[0]
    return f'{w:g} × {h:g} m'


def _texture(asset: dict) -> dict:
    maps = set((asset.get('attributes') or {}).get('maps') or [])
    size = _size_hint(asset)
    packed = 'arm' in maps
    scale = f' One tile covers about {size} in the real world; scale UVs to match.' if size else ''
    godot = [
        'Create a StandardMaterial3D: Albedo → colour/diffuse map; enable Normal Map → the OpenGL normal '
        '(nor_gl / NormalGL); Roughness → roughness map (Texture Channel: Red); enable Ambient Occlusion → AO map.',
        'Metallic surfaces: Metallic = 1 and Metallic Texture → metalness map.' if 'metalness' in maps
        else 'Leave Metallic at 0 unless the material is metal.',
        'Displacement is optional: enable Height and use a small scale (0.02–0.05).',
        'For big surfaces enable UV1 Triplanar (World Triplanar for terrain) instead of hand-tuning UVs.' + scale,
    ]
    if (asset.get('attributes') or {}).get('godot_material'):
        godot.insert(0, 'Shortcut: the ambientCG zip already contains a Godot material (.tres) wired to these '
                        'maps; drag it onto your mesh. The steps below explain the wiring.')
    if packed:
        godot.insert(1, 'Or use ORMMaterial3D with the packed “arm” map (AO = R, Roughness = G, Metallic = B).')
    threejs = [
        'const tl = new THREE.TextureLoader(); load each map; set colorMap.colorSpace = THREE.SRGBColorSpace '
        '(all other maps stay linear).',
        'new THREE.MeshStandardMaterial({ map: colorMap, normalMap: norGL, roughnessMap, aoMap }) — use the '
        'OpenGL normal (nor_gl / NormalGL).',
        'Tile it: for each map set wrapS = wrapT = THREE.RepeatWrapping and repeat.set(n, n).' + scale,
    ]
    unity = [
        'URP/HDRP Lit material: Base Map → colour map; Normal Map → nor_gl / NormalGL '
        '(set its Texture Type to Normal map).',
        'Unity uses smoothness, not roughness: invert the roughness map into the alpha of the Metallic map, '
        'or use a Shader Graph with a One Minus node.',
        'Occlusion → AO map (HDRP: pack into the mask map).',
    ]
    unreal = [
        'Use the DirectX normal (nor_dx / NormalDX). Import roughness, AO and metalness with sRGB off '
        '(Compression: Masks).',
        'Packed “arm” maps plug straight in: R → Ambient Occlusion, G → Roughness, B → Metallic.' if packed else
        'Wire Base Color, Normal, Roughness and Ambient Occlusion into the material’s inputs.',
    ]
    blender = [
        'With Node Wrangler, select the Principled BSDF and press Ctrl+Shift+T to load every map at once.',
        'Set every map except the colour map to Non-Color. Poly Haven also offers a ready .blend variant.',
    ]
    return {'godot': godot, 'threejs': threejs, 'unity': unity, 'unreal': unreal, 'blender': blender}


def _hdri(asset: dict) -> dict:
    return {
        'godot': [
            'WorldEnvironment → Environment → Background: Sky; Sky → Sky Material: PanoramaSkyMaterial → '
            'Panorama: the .hdr/.exr file.',
            'Set Ambient Light and Reflected Light Source to Sky so the HDRI also lights the scene.',
            'Large files: 2K–4K is plenty for lighting; use 8K+ only when the sky is seen directly.',
        ],
        'threejs': [
            'new RGBELoader() (HDRLoader in newer three.js) or EXRLoader → texture.mapping = '
            'THREE.EquirectangularReflectionMapping.',
            'scene.environment = texture for lighting; scene.background = texture to show it.',
        ],
        'unity': [
            'Import the .hdr/.exr with Texture Shape: Cube; create a Skybox/Cubemap material.',
            'Lighting → Environment → Skybox Material, then regenerate lighting.',
        ],
        'unreal': [
            'Import the .hdr/.exr as a cubemap; use the HDRI Backdrop plugin, or a Sky Light with '
            'Source Type: Specified Cubemap.',
        ],
        'blender': ['World properties → Color → Environment Texture → open the .hdr/.exr.'],
    }


def _model(asset: dict) -> dict:
    formats = set(asset.get('formats') or [])
    scale = ' Units are metres (real-world scale).' if asset.get('dimensions') else ''
    if 'gltf' in formats:
        first = 'Copy the whole folder (.gltf + .bin + textures/) into res:// — Godot imports glTF as a scene automatically.'
    elif 'glb' in formats:
        first = 'Copy the .glb files you need into res:// — Godot imports each one as a scene automatically.'
    elif 'blend' in formats and not formats & {'fbx', 'obj', 'dae'}:
        first = ('This entry ships .blend files: Godot 4 imports them directly when Blender is installed (Editor '
                 'Settings → FileSystem → Import → Blender path); otherwise export glTF from Blender.')
    else:
        first = 'Godot 4 imports glTF and FBX natively; prefer the glTF variant.'
    return {
        'godot': [
            first + scale,
            'Instance it in your level. For static props open Advanced Import Settings and set Physics → '
            'Static Body with a Convex (or Trimesh) shape.',
        ],
        'threejs': [
            "import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'; "
            "new GLTFLoader().load('model.gltf', (g) => scene.add(g.scene));",
            'Keep the .bin and textures/ beside the .gltf. To ship one file: '
            'npx @gltf-transform/cli copy model.gltf model.glb',
        ],
        'unity': ['Install glTFast (com.unity.cloud.gltfast) to import .gltf/.glb, or use the FBX variant.'],
        'unreal': ['Unreal 5 imports glTF natively (Interchange); FBX works too.'],
        'blender': ['File → Import → glTF 2.0 (or open the .blend variant when offered).'],
    }


def _sound(asset: dict) -> dict:
    original = (asset.get('attributes') or {}).get('original') or {}
    extra = []
    if asset.get('source') == 'freesound':
        kind = (original.get('type') or 'original').upper()
        extra = [f'These files are Freesound’s high-quality previews. For the {kind} original, download it from the '
                 'sound’s Freesound page (free login).']
    notes = {
        'godot': [
            'Put .ogg/.wav files in res://; play with AudioStreamPlayer (2D/UI) or AudioStreamPlayer3D '
            '(positional).',
            'For ambience and music loops enable Loop in the Import dock, then Reimport.',
        ],
        'threejs': [
            'THREE.AudioLoader + THREE.Audio (or PositionalAudio on an object); browsers start audio only after '
            'a user gesture.',
        ],
        'unity': ['Short SFX: Load Type Decompress On Load; music/ambience: Streaming.'],
        'unreal': ['Import WAV; wrap in a MetaSound or Sound Cue for random pitch/volume variation.'],
        'blender': ['Video Sequencer → Add → Sound.'],
    }
    return {engine: steps + extra for engine, steps in notes.items()}


def _music(asset: dict) -> dict:
    text = ' '.join([*(asset.get('tags') or []), asset.get('description') or '']).lower()
    loop = ' (the author marks it as loopable)' if 'loop' in text else ''
    notes = {
        'godot': [
            'Put the .ogg in res:// and play it with an AudioStreamPlayer (Autoplay for level music; set its Bus '
            'to a Music bus so players can change the volume).',
            f'For background music enable Loop in the Import dock, then Reimport{loop}.',
        ],
        'threejs': [
            'Background music needs no 3D audio: const music = new Audio(url); music.loop = true; call '
            'music.play() after the first click or key press (browsers block autoplay).',
        ],
        'unity': ['AudioClip Load Type: Streaming; an AudioSource with Loop and Play On Awake for level music.'],
        'unreal': ['Import the WAV or OGG as a Sound Wave, tick Looping, and start it on BeginPlay (or use a '
                   'MetaSound).'],
        'blender': ['Video Sequencer → Add → Sound.'],
    }
    if asset.get('source') == 'opengameart' and 'wav' in (asset.get('formats') or []):
        for steps in notes.values():
            steps.append('The original here is WAV (large); the OGG download is the same track, game-ready.')
    return notes


# Credit boxes that only restate the licence ("CC0", "CCO", "public domain", "none") ask for nothing.
_NO_REQUEST = re.compile(r'^\W*(?:licen[cs]e[d]?\s*(?:under)?:?\s*)?(?:cc[\s-]*(?:0|o|zero)(?:\s*1\.0)?|public[\s-]*domain|'
                         r'none|n/?a|no|nothing|not (?:needed|required|necessary)|'
                         r'no (?:attribution|credit)s?(?: is)?(?: required| needed| necessary)?|'
                         r'(?:attribution|credit)s? (?:is )?not (?:required|needed|necessary))\W*$', re.I)


def source_notes(asset: dict) -> list[str]:
    """What to know about where this entry comes from (shown to people and agents)."""
    if asset.get('source') != 'opengameart':
        return []
    attributes = asset.get('attributes') or {}
    notes = ['Licence as declared by the uploader on OpenGameArt; the page lists the files exactly as they '
             'shared them.']
    offered = [name for name in attributes.get('licenses_offered') or [] if name.strip().upper() != 'CC0']
    if offered:
        notes.append(f'Also offered under {", ".join(offered)}; Asset Commons uses the CC0 option.')
    notice = (attributes.get('copyright_notice') or '').strip()
    if notice and not _NO_REQUEST.match(notice):
        notes.append(f'The author asks: “{notice[:400]}” (optional under CC0, but kind to honour).')
    if attributes.get('details') != 'complete':
        notes.append('Details and files are still being read from OpenGameArt (one page every ten seconds, '
                     'as the site asks).')
    return notes


def _animation(asset: dict) -> dict:
    return {
        'godot': [
            'glTF/FBX animations import into an AnimationPlayer; retarget to your own rig with a BoneMap and '
            'SkeletonProfileHumanoid in Advanced Import Settings.',
        ],
        'threejs': [
            'const mixer = new THREE.AnimationMixer(gltf.scene); mixer.clipAction(gltf.animations[0]).play(); '
            'call mixer.update(delta) every frame.',
        ],
        'unity': ['Rig → Animation Type: Humanoid to retarget clips onto other humanoids.'],
        'unreal': ['Retarget onto your skeleton with an IK Retargeter.'],
        'blender': ['Import glTF/FBX; clips appear as Actions in the Action Editor / NLA.'],
    }


def _sprite(asset: dict) -> dict:
    pixel = asset.get('style') == 'pixel'
    filter_note = ' Pixel art: set Texture Filter to Nearest (Project Settings → Rendering → Textures).' if pixel else ''
    return {
        'godot': ['Copy the PNGs into res://; use Sprite2D for single images and AnimatedSprite2D for frame '
                  'sequences.' + filter_note,
                  'For tile sheets, add a TileMapLayer with a TileSet atlas built from the sheet (set the tile size).'],
        'threejs': ["new THREE.TextureLoader().load('sprite.png') on a THREE.Sprite or a plane; set "
                    "texture.colorSpace = THREE.SRGBColorSpace" + (' and magFilter = THREE.NearestFilter' if pixel else '')
                    + '.'],
        'unity': ['Texture Type: Sprite (2D and UI); for sheets use Sprite Mode: Multiple and slice them in the Sprite '
                  'Editor.' + (' Filter Mode: Point, Compression: None.' if pixel else '')],
        'unreal': ['Use Paper2D: Create Sprite from each texture, or Extract Sprites from a sheet.'],
        'blender': ['Import Images as Planes (built-in add-on) to place sprites in a scene.'],
    }


def _ui(asset: dict) -> dict:
    return {
        'godot': ['Use TextureRect / TextureButton for icons and buttons, NinePatchRect for stretchable panels.',
                  'Fonts: drop the .ttf/.otf into res:// and assign it in a Theme or the control’s theme overrides.'],
        'threejs': ['UI usually lives in HTML/CSS over the canvas; use the PNGs as <img> or CSS backgrounds.'],
        'unity': ['Texture Type: Sprite (2D and UI); set borders in the Sprite Editor for 9-slicing in UI Images.'],
        'unreal': ['Import as textures and use them in UMG widgets (set Draw As: Box for 9-slice panels).'],
        'blender': ['Not usually needed in Blender; use the PNGs in your game engine’s UI.'],
    }


def _pack_notes(asset: dict) -> dict:
    """Extra steps that depend on how a pack is laid out."""
    attributes = asset.get('attributes') or {}
    if not attributes.get('pack'):
        return {}
    if asset.get('source') == 'kenney':
        if asset.get('type') == 'model' or 'model' in (asset.get('extra_types') or []):
            first = ('The zip has Models/GLB format, Models/FBX format and Models/OBJ format, plus Previews/ with a PNG '
                     'per model. Use the GLB files for Godot and three.js.')
        else:
            first = 'The zip holds the pack’s files plus License.txt; Kenney packs usually include a Preview.png.'
        return {engine: [first] for engine in ENGINES}
    manual = attributes.get('manual_download')
    if manual:
        return {engine: [f'Download the pack by hand first: {manual["note"]} ({manual["url"]})'] for engine in ENGINES}
    return {}


_BUILDERS = {'texture': _texture, 'hdri': _hdri, 'model': _model, 'sound': _sound, 'music': _music,
             'animation': _animation, 'sprite': _sprite, 'ui': _ui}


def notes(asset: dict, engine: str | None = None) -> dict:
    """{engine_id: [steps]} for every engine, or only the one asked for."""
    builder = _BUILDERS.get(asset.get('type'))
    if not builder:
        return {}
    every = builder(asset)
    for engine_key, steps in _pack_notes(asset).items():
        every[engine_key] = steps + every.get(engine_key, [])
    if 'animation' in (asset.get('extra_types') or []) and asset.get('type') != 'animation':
        for engine_key, steps in _animation(asset).items():
            every[engine_key] = every.get(engine_key, []) + steps
    chosen = engine_id(engine)
    if chosen:
        return {chosen: every.get(chosen, [])}
    return every
