import os, sys, json, base64, time, subprocess, shutil
from typing import List, Optional
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
import uvicorn

# Set Google credentials path
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = r"C:\Users\info\AppData\Roaming\gcloud\application_default_credentials.json"

from google import genai
from google.genai import types

app = FastAPI(title="ViralFlow Video Producer API")
client = genai.Client(vertexai=True, project='root-bricolage-491415-q4', location='us-central1')

class Scene(BaseModel):
    prompt: str
    duration: float = 5.0
    type: str = "video"  # video or image

class RenderRequest(BaseModel):
    scenes: List[Scene]
    tts_audio_base64: str
    music_file: Optional[str] = "Pyramid Background Music No Copyright.mp3"

@app.post("/render")
def render_video(req: RenderRequest):
    workdir = r"C:\Users\info\N8N-ViralFlow\video_project"
    assets_dir = os.path.join(workdir, "assets")
    os.makedirs(assets_dir, exist_ok=True)
    
    # 1. Decode and save TTS audio
    vo_path = os.path.join(assets_dir, "voiceover.mp3")
    print(f"Saving TTS audio to {vo_path}...")
    try:
        audio_bytes = base64.b64decode(req.tts_audio_base64)
        with open(vo_path, "wb") as f:
            f.write(audio_bytes)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to decode TTS audio: {e}")

    # 2. Run HyperFrames transcribe to get word timings
    print("Running HyperFrames transcribe...")
    transcript_path = os.path.join(workdir, "transcript.json")
    try:
        # Run transcription via hyperframes transcribe
        subprocess.run(["npx", "hyperframes", "transcribe", vo_path, "-o", transcript_path], check=True, shell=True)
    except Exception as e:
        print(f"HyperFrames transcription failed: {e}. Falling back to default spacing...")
        # Create a dummy timing transcript if transcription fails
        words = []
        words.append({"word": "Viral", "start": 0.0, "end": 1.0})
        words.append({"word": "Video", "start": 1.0, "end": 2.0})
        with open(transcript_path, "w") as f:
            json.dump({"words": words}, f)

    # 3. Generate visuals for each scene
    scene_files = []
    for i, s in enumerate(req.scenes):
        print(f"Generating visual for Scene {i+1}/{len(req.scenes)}: {s.prompt[:50]}...")
        if s.type == "video":
            out_file = os.path.join(assets_dir, f"scene_{i}.mp4")
            try:
                operation = client.models.generate_videos(
                    model='veo-2.0-generate-001',
                    prompt=s.prompt,
                    config=types.GenerateVideosConfig(
                        aspect_ratio='9:16',
                        duration_seconds=int(s.duration),
                        person_generation='allow_all',
                    )
                )
                print(f"  Veo job started: {operation.name}")
                while not operation.done:
                    time.sleep(10)
                    operation = client.operations.get(operation)
                
                if operation.error:
                    raise Exception(operation.error)
                
                # Save MP4
                video_bytes = operation.response.generated_videos[0].video.video_bytes
                with open(out_file, "wb") as f:
                    f.write(video_bytes)
                scene_files.append({"type": "video", "path": f"assets/scene_{i}.mp4", "duration": s.duration})
                print(f"  ✅ Video saved: {out_file}")
            except Exception as e:
                print(f"  ⚠️ Veo failed: {e}. Falling back to Imagen...")
                s.type = "image" # Fallback to image

        if s.type == "image":
            out_file = os.path.join(assets_dir, f"scene_{i}.png")
            try:
                response = client.models.generate_images(
                    model='imagen-3.0-generate-002',
                    prompt=s.prompt,
                    config=types.GenerateImagesConfig(
                        number_of_images=1,
                        aspect_ratio='9:16',
                        output_mime_type='image/png'
                    )
                )
                img_bytes = response.generated_images[0].image.image_bytes
                with open(out_file, "wb") as f:
                    f.write(img_bytes)
                scene_files.append({"type": "image", "path": f"assets/scene_{i}.png", "duration": s.duration})
                print(f"  ✅ Image saved: {out_file}")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Generation failed for scene {i+1}: {e}")

    # Copy background music if exists
    music_src = os.path.join(r"C:\Users\info\N8N-ViralFlow\n8n-data\nca-toolkit-music", req.music_file or "")
    music_dest = os.path.join(assets_dir, "music.mp3")
    if os.path.exists(music_src):
        shutil.copy(music_src, music_dest)
        print(f"Background music copied: {music_dest}")
    else:
        print(f"Music source not found at {music_src}, skipping background music.")

    # 4. Generate the index.html HyperFrames Composition
    html_path = os.path.join(workdir, "index.html")
    print(f"Generating HyperFrames HTML composition at {html_path}...")
    
    # Generate HTML string
    html_content = """<!DOCTYPE html>
<html data-composition-id="main" data-width="1080" data-height="1920">
<head>
  <meta charset="UTF-8">
  <style>
    body { margin: 0; background: #000; overflow: hidden; font-family: 'Poppins', sans-serif; }
    .scene-container { position: absolute; inset: 0; width: 100%; height: 100%; }
    .sc-img { width: 100%; height: 100%; object-fit: cover; }
    .sc-vid { width: 100%; height: 100%; object-fit: cover; }
    
    /* Caption highlight style */
    .caption-container {
      position: absolute;
      bottom: 25%;
      left: 5%;
      right: 5%;
      text-align: center;
      z-index: 100;
    }
    .word {
      font-size: 75px;
      font-weight: 900;
      color: #fff;
      text-shadow: 0 0 20px rgba(0,0,0,0.8), 0 0 10px rgba(0,0,0,0.8);
      display: inline-block;
      margin: 0 10px;
      transform: scale(0.9);
      opacity: 0.5;
      transition: all 0.1s ease-out;
    }
    .word.active {
      color: #00ffcc;
      transform: scale(1.15) rotate(-2deg);
      opacity: 1;
      text-shadow: 0 0 30px #00ffcc, 0 0 10px rgba(0,0,0,1);
    }
  </style>
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
</head>
<body>

  <!-- Audio Elements -->
  <audio id="voiceover" src="assets/voiceover.mp3" data-start="0"></audio>
"""
    if os.path.exists(music_dest):
        html_content += '  <audio id="music" src="assets/music.mp3" data-start="0" data-volume="0.15"></audio>\n'

    # Build visual scenes
    current_time = 0.0
    for i, sf in enumerate(scene_files):
        track = i + 1
        start_attr = f"{current_time}"
        duration_attr = f'data-duration="{sf["duration"]}"'
        
        if sf["type"] == "video":
            html_content += f"""
  <video id="scene_{i}" class="clip" src="{sf["path"]}" muted playsinline
         data-start="{start_attr}" {duration_attr} data-track-index="{track}"
         style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;"></video>
"""
        else: # image with Ken Burns effect
            html_content += f"""
  <div id="scene_{i}" class="clip scene-container" data-start="{start_attr}" {duration_attr} data-track-index="{track}">
    <img class="sc-img" src="{sf["path"]}">
  </div>
"""
        current_time += sf["duration"]

    # Add the caption overlay layer
    html_content += f"""
  <!-- Caption Container -->
  <div class="caption-container" id="captions" class="clip" data-start="0" data-duration="{current_time}" data-track-index="100"></div>

  <script>
    window.__timelines = window.__timelines || {{}};
    const tl = gsap.timeline({{ paused: true }});

    // 1. Zoom/Pan animation for each image scene (Ken Burns)
"""
    # Insert Ken Burns zoom animations for image scenes
    current_time_kb = 0.0
    for i, sf in enumerate(scene_files):
        if sf["type"] == "image":
            html_content += f"    tl.fromTo('#scene_{i} .sc-img', {{ scale: 1.0 }}, {{ scale: 1.15, duration: {sf['duration']}, ease: 'sine.inOut' }}, {current_time_kb});\n"
        current_time_kb += sf["duration"]

    # Load transcript and insert word level highlights
    try:
        with open(transcript_path, "r") as f:
            t_data = json.load(f)
            words = t_data.get("words", [])
    except Exception:
        words = []

    # Insert captions html structure dynamically
    html_content += "\n    // 2. Word timing highlights\n"
    captions_container_html = ""
    for idx, w in enumerate(words):
        word_text = w["word"].replace("'", "\\'").replace('"', '\\"')
        captions_container_html += f'<span class="word" id="w_{idx}">{word_text}</span>'
        
        # GSAP triggers to activate/deactivate words based on start/end timestamps
        html_content += f"    tl.to('#w_{idx}', {{ className: 'word active', duration: 0.05 }}, {w['start']});\n"
        html_content += f"    tl.to('#w_{idx}', {{ className: 'word', duration: 0.05 }}, {w['end']});\n"

    html_content += f"""
    // Inject the word spans into container
    document.getElementById('captions').innerHTML = '{captions_container_html}';

    // Extend timeline to final duration
    tl.set({{}}, {{}}, {current_time});
    window.__timelines["main"] = tl;
  </script>
</body>
</html>
"""
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    # 5. Render final MP4 on the host
    out_mp4 = os.path.join(r"C:\Users\info\N8N-ViralFlow\n8n-data", "video_output.mp4")
    print(f"Rendering final MP4 to {out_mp4} using HyperFrames render...")
    try:
        # Run HyperFrames render
        subprocess.run(["npx", "hyperframes", "render", "--output", out_mp4, "--resolution", "portrait"], cwd=workdir, check=True, shell=True)
        print("  🎉 Render COMPLETE!")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"HyperFrames render failed: {e}")

    return {
        "status": "success",
        "video_path": "video_output.mp4"
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
