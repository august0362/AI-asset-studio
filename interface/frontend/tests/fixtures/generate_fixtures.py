"""M1 fixtures: deterministic standard-library-only PNG + textured glTF 2.0 box.

Run from any working directory. M2's Pillow runtime is intentionally not needed here.
JSON fixtures mirror CONTRACTS v1.0 and are consumed by the mock client and tests.
"""
import hashlib
import json
import math
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ART = ROOT / 'artifacts'
CON = ROOT / 'contracts'
ART.mkdir(parents=True, exist_ok=True)
CON.mkdir(parents=True, exist_ok=True)


def png(width, height, pixels):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    rows = b''.join(b'\x00' + bytes(pixels[y*width*3:(y+1)*width*3]) for y in range(height))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(rows, 9)) + chunk(b'IEND', b'')


size = 768
pixels = bytearray()
for y in range(size):
    for x in range(size):
        glow = max(0, 1 - math.hypot((x-384)/420, (y-400)/460))
        grid = 5 if (x % 48 == 0 or y % 48 == 0) else 0
        pixels.extend((int(10 + glow*4), int(15 + glow*15 + grid), int(25 + glow*23 + grid)))


def polygon(points, color):
    for y in range(max(0, min(p[1] for p in points)), min(size, max(p[1] for p in points)+1)):
        intersections = []
        for a, b in zip(points, points[1:]+points[:1]):
            if min(a[1], b[1]) <= y < max(a[1], b[1]):
                intersections.append(int(a[0] + (y-a[1])*(b[0]-a[0])/(b[1]-a[1])))
        intersections.sort()
        for left, right in zip(intersections[::2], intersections[1::2]):
            for x in range(max(0, left), min(size, right+1)):
                i = (y*size+x)*3
                pixels[i:i+3] = bytes(color)


# Deliberately a simple fixture, not purported AI output.
polygon([(175, 536), (384, 431), (593, 536), (384, 643)], (23, 48, 65))
polygon([(175, 536), (384, 643), (384, 660), (175, 553)], (17, 30, 47))
polygon([(384, 643), (593, 536), (593, 553), (384, 660)], (15, 38, 50))
polygon([(240, 286), (384, 212), (528, 286), (384, 361)], (98, 218, 239))
polygon([(240, 286), (384, 361), (384, 558), (240, 483)], (25, 113, 146))
polygon([(384, 361), (528, 286), (528, 483), (384, 558)], (38, 161, 188))
polygon([(277, 329), (346, 365), (346, 489), (277, 453)], (60, 187, 211))
polygon([(421, 370), (492, 334), (492, 455), (421, 492)], (26, 111, 144))
polygon([(354, 295), (384, 279), (414, 295), (384, 311)], (208, 250, 255))
# Small pixels to emphasize synthetic fixture artwork.
for x, y in [(160, 250), (600, 320), (286, 160), (540, 200), (204, 420)]:
    polygon([(x, y-5), (x+5, y), (x, y+5), (x-5, y)], (76, 215, 246))
image = png(size, size, pixels)
(ART / 'mock.png').write_bytes(image)
texture = png(2, 2, [65, 197, 225, 91, 211, 235, 91, 211, 235, 35, 152, 184])

positions, normals, uv, indices = [], [], [], []
faces = [([(1,-1,-1),(1,1,-1),(1,1,1),(1,-1,1)], (1,0,0)),
         ([(-1,-1,1),(-1,1,1),(-1,1,-1),(-1,-1,-1)], (-1,0,0)),
         ([(-1,1,-1),(-1,1,1),(1,1,1),(1,1,-1)], (0,1,0)),
         ([(-1,-1,1),(-1,-1,-1),(1,-1,-1),(1,-1,1)], (0,-1,0)),
         ([(1,-1,1),(1,1,1),(-1,1,1),(-1,-1,1)], (0,0,1)),
         ([(-1,-1,-1),(-1,1,-1),(1,1,-1),(1,-1,-1)], (0,0,-1))]
for points, normal in faces:
    start = len(positions)//3
    positions.extend(v*0.75 for point in points for v in point)
    normals.extend(normal*4)
    uv.extend([0,0,0,1,1,1,1,0])
    indices.extend(start+i for i in [0,1,2,0,2,3])
binary = bytearray()
views = []
for data in [struct.pack('<72f', *positions), struct.pack('<72f', *normals), struct.pack('<48f', *uv), struct.pack('<36H', *indices), texture]:
    while len(binary) % 4: binary.append(0)
    views.append({'buffer': 0, 'byteOffset': len(binary), 'byteLength': len(data)})
    binary.extend(data)
gltf = {'asset': {'version': '2.0', 'generator': 'AI Asset Studio M1 standard library fixture'}, 'scene': 0,
        'scenes': [{'nodes': [0]}], 'nodes': [{'mesh': 0, 'name': 'Mock textured box'}],
        'meshes': [{'primitives': [{'attributes': {'POSITION': 0, 'NORMAL': 1, 'TEXCOORD_0': 2}, 'indices': 3, 'material': 0}]}],
        'materials': [{'name': 'Mock cyan ceramic', 'pbrMetallicRoughness': {'baseColorTexture': {'index': 0}, 'metallicFactor': 0.25, 'roughnessFactor': 0.38}}],
        'textures': [{'source': 0}], 'images': [{'bufferView': 4, 'mimeType': 'image/png'}],
        'accessors': [{'bufferView': 0, 'componentType': 5126, 'count': 24, 'type': 'VEC3', 'min': [-0.75]*3, 'max': [0.75]*3},
                      {'bufferView': 1, 'componentType': 5126, 'count': 24, 'type': 'VEC3'},
                      {'bufferView': 2, 'componentType': 5126, 'count': 24, 'type': 'VEC2'},
                      {'bufferView': 3, 'componentType': 5123, 'count': 36, 'type': 'SCALAR'}],
        'bufferViews': views, 'buffers': [{'byteLength': len(binary)}]}
encoded = json.dumps(gltf, separators=(',', ':')).encode()
encoded += b' ' * (-len(encoded) % 4)
binary += b'\x00' * (-len(binary) % 4)
glb = struct.pack('<III', 0x46546c67, 2, 12+8+len(encoded)+8+len(binary)) + struct.pack('<II', len(encoded), 0x4e4f534a) + encoded + struct.pack('<II', len(binary), 0x004e4942) + binary
(ART / 'mock.glb').write_bytes(glb)


def save(name, obj):
    (CON / (name+'.json')).write_text(json.dumps(obj, indent=2)+'\n', encoding='utf-8')


categories = ['character', 'skill_effect', 'weapon', 'companion']
roles = ['front', 'side', 'back', 'three_quarter', 'detail', 'style_reference']
save('catalog', {'contract_version': '1.0', 'pipelines': [
    {'pipeline_type': p, 'display_name': label, 'availability': availability, 'output_formats': [fmt]}
    for p, label, availability, fmt in [('text_to_2d','Text → 2D','available','png'), ('image_to_3d','Image → 3D','available','glb'), ('text_to_3d','Text → 3D','planned','glb')]],
    'asset_categories': categories, 'image_roles': roles, 'limits': {'max_upload_bytes': 52428800, 'max_images_per_request': 8, 'prompt_max_length': 4000, 'supported_upload_mime_types': ['image/png','image/jpeg','image/webp']}})
seed = {'type': 'integer', 'minimum': 0, 'maximum': 4294967295, 'default': None}
models = []
for id_, label, pipeline, cats, prompt, min_images, max_images, allowed, required, kinds, vram, runtime, availability in [
    ('mock-t2d-basic', 'Mock Basic Text→2D', 'text_to_2d', categories, True, 0, 0, [], [], ['cpu','gpu_cuda'], None, 30, 'available'),
    ('mock-t2d-styleref', 'Mock Style Reference Text→2D', 'text_to_2d', categories, True, 0, 1, ['style_reference'], [], ['gpu_cuda'], None, 60, 'experimental'),
    ('mock-i3d-single', 'Mock Single Image→3D', 'image_to_3d', ['character','weapon','companion'], False, 1, 1, ['front'], ['front'], ['gpu_cuda'], None, 120, 'available'),
    ('mock-i3d-multiview', 'Mock Multiview Image→3D', 'image_to_3d', ['character','companion'], False, 2, 4, ['front','side','back','detail'], ['front','side'], ['gpu_cuda'], 12884901888, 900, 'available'),
    ('mock-t3d-basic', 'Mock Basic Text→3D', 'text_to_3d', categories, True, 0, 0, [], [], ['gpu_cuda'], None, None, 'planned')]:
    multi = id_ == 'mock-i3d-multiview'
    inp = {'prompt_supported': prompt, 'prompt_required': prompt, 'prompt_max_length': 1000 if prompt else None, 'min_images': min_images, 'max_images': max_images,
           'supported_image_roles': allowed, 'required_image_roles': required,
           'supported_mime_types': (['image/png','image/jpeg','image/webp'] if id_ == 'mock-t2d-styleref' else ['image/png','image/jpeg']) if max_images else None,
           'maximum_file_size_bytes': (20971520 if multi else 52428800) if max_images else None,
           'min_image_width': 512 if multi else None, 'min_image_height': 512 if multi else None,
           'max_image_width': 4096 if multi else None, 'max_image_height': 4096 if multi else None}
    opts = {'seed': seed}
    if id_ == 'mock-t2d-basic':
        opts.update({k: {'type': 'integer', 'enum': [512,768,1024], 'default': 1024} for k in ['width','height']})
        opts['negative_prompt'] = {'type': 'string', 'max_length': 1000, 'default': None}
    if multi: opts['texture_resolution'] = {'type': 'integer', 'enum': [1024,2048], 'default': 1024}
    unknown = []
    if vram is None and kinds == ['gpu_cuda']: unknown.append('runtime.minimum_gpu_vram_bytes')
    if runtime is None: unknown.append('runtime.estimated_runtime_seconds')
    models.append({'contract_version': '1.0', 'model_id': id_, 'display_name': label, 'adapter': 'mock_'+pipeline,
                   'is_mock': True, 'availability': availability, 'supported_pipeline_types': [pipeline], 'supported_asset_categories': cats, 'inputs': inp,
                   'supported_output_formats': ['png' if pipeline == 'text_to_2d' else 'glb'],
                   'runtime': {'supported_accelerators': kinds, 'multi_gpu': 'optional' if multi else 'unsupported', 'minimum_gpu_vram_bytes': vram, 'estimated_runtime_seconds': runtime},
                   'options_schema': opts, 'unknown_requirements': unknown})
save('models', {'models': models})
save('profiles', {'profiles': [{'contract_version':'1.0','profile_id':'default','display_name':'Owner Kaggle','owner_label':'project-owner','mode':'mock','enabled':True,'authorization_confirmed':True,
    'accelerators':[{'accelerator_id': id_, 'kind': kind, 'device_count': n, 'vram_bytes_per_device': mem, 'max_session_seconds': limit}
    for id_,kind,n,mem,limit in [('cpu','cpu',0,None,43200),('gpu_p100','gpu_cuda',1,17179869184,43200),('gpu_t4x2','gpu_cuda',2,16106127360,43200),('tpu_vm','tpu',1,None,32400)]]}]})
stamp = '2026-11-06T10:20:05Z'
snapshot = {'contract_version':'1.0','compute_profile_id':'default','authentication_status':'authenticated','accelerator_type':'gpu_t4x2',
            'accelerator_availability':[{'accelerator_id':'gpu_t4x2','status':'available'},{'accelerator_id':'tpu_vm','status':'unknown'}],
            'gpu_quota_total_hours':30.0,'gpu_quota_used_hours':11.5,'gpu_quota_remaining_hours':18.5,
            'tpu_quota_total_hours':None,'tpu_quota_used_hours':None,'tpu_quota_remaining_hours':None,'quota_reset_at':None,
            'session_started_at':'2026-11-06T10:17:40Z','estimated_session_remaining_seconds':41100,'session_status':'running',
            'cpu_utilization_percent':63.5,'ram_used_bytes':9663676416,'ram_total_bytes':33285996544,
            'gpu_devices':[{'index':0,'name':'Tesla T4','utilization_percent':97.0,'vram_used_bytes':13421772800,'vram_total_bytes':16106127360,'temperature_c':71.0,'status':'available'},
                           {'index':1,'name':'Tesla T4','utilization_percent':4.0,'vram_used_bytes':524288000,'vram_total_bytes':16106127360,'temperature_c':None,'status':'available'}],
            'observed_at':{k:stamp for k in ['snapshot','quota','session','host','gpu']}, 'source':{k:'mock' for k in ['quota','session','host','gpu']},
            'freshness_status':{k:'fresh' for k in ['quota','session','host','gpu']},
            'error':[{'code':'COMPUTE_TPU_QUOTA_UNAVAILABLE','severity':'warning','field':'tpu_quota_total_hours','message':'TPU quota is not reported in this mock scenario.','details':{},'retryable':True}]}
save('snapshot', snapshot)
save('artifact-metadata', {fmt: {'size_bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'width':size if fmt=='png' else None,'height':size if fmt=='png' else None} for fmt,data in [('png',image),('glb',glb)]})
print(f'Generated {len(models)} model records, catalog, profile, snapshot, and PNG ({len(image)} bytes) / GLB ({len(glb)} bytes).')
