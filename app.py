import os, re, tempfile, asyncio, textwrap
import requests
import streamlit as st
import edge_tts
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips, CompositeVideoClip, TextClip

st.set_page_config(page_title="Script to Video AI", page_icon="🎬", layout="centered")
st.title("🎬 Script to Video")
st.write("Paste a script to create a simple video with English narration, relevant images, and subtitles.")
st.caption("Free starter version • Internet connection required • Public deployment needs setup")

script = st.text_area("Your script", height=220, placeholder="Paste your video script here...")
voice = st.selectbox("English voice", ["en-US-AriaNeural", "en-US-GuyNeural", "en-GB-SoniaNeural", "en-GB-RyanNeural"])
ratio = st.selectbox("Video format", ["16:9 YouTube", "9:16 Shorts/Reels"])
title = st.text_input("Optional video title", "My Video")

def split_sentences(text):
    chunks = re.split(r'(?<=[.!?])\s+', text.strip())
    return [c.strip() for c in chunks if c.strip()]

def search_image(query, out_path):
    url = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f"filetype:bitmap {query}", "gsrnamespace": 6,
        "gsrlimit": 8, "prop": "imageinfo", "iiprop": "url",
        "iiurlwidth": 1280
    }
    try:
        data = requests.get(url, params=params, timeout=20, headers={"User-Agent":"ScriptToVideoStarter/1.0"}).json()
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            info = page.get("imageinfo", [{}])[0]
            img_url = info.get("thumburl") or info.get("url")
            if img_url and img_url.lower().split("?")[0].endswith((".jpg",".jpeg",".png",".webp")):
                r = requests.get(img_url, timeout=25, headers={"User-Agent":"ScriptToVideoStarter/1.0"})
                if r.ok and len(r.content) > 5000:
                    with open(out_path, "wb") as f: f.write(r.content)
                    return True
    except Exception:
        pass
    return False

async def make_voice(text, voice, path):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(path)

if st.button("Create video", type="primary", use_container_width=True):
    if not script.strip():
        st.error("Please paste a script first.")
        st.stop()
    try:
        from PIL import Image, ImageDraw
        from moviepy.editor import ColorClip
        with tempfile.TemporaryDirectory() as tmp:
            status = st.status("Preparing your video...", expanded=True)
            sentences = split_sentences(script)
            if not sentences:
                st.error("Please enter a longer script.")
                st.stop()
            voice_path = os.path.join(tmp, "narration.mp3")
            status.write("Creating English narration...")
            asyncio.run(make_voice(script, voice, voice_path))
            audio = AudioFileClip(voice_path)
            W, H = (1080, 1920) if ratio.startswith("9:16") else (1920, 1080)
            clips = []
            per = audio.duration / len(sentences)
            for i, sentence in enumerate(sentences):
                status.write(f"Finding image {i+1} of {len(sentences)}...")
                words = re.sub(r'[^a-zA-Z0-9 ]', ' ', sentence).split()
                query = " ".join(words[:6]) or "nature"
                img_path = os.path.join(tmp, f"img_{i}.jpg")
                ok = search_image(query, img_path)
                if not ok:
                    # Create a clean fallback card if no suitable image is found.
                    im = Image.new("RGB", (W, H), (25, 35, 55))
                    draw = ImageDraw.Draw(im)
                    wrapped = textwrap.fill(sentence, width=22 if H > W else 45)
                    draw.multiline_text((80, H//2-100), wrapped, fill="white", spacing=14)
                    img_path = os.path.join(tmp, f"fallback_{i}.jpg")
                    im.save(img_path, quality=90)
                clip = ImageClip(img_path).set_duration(per)
                clip = clip.resize(height=H) if clip.w/clip.h < W/H else clip.resize(width=W)
                clip = clip.crop(x_center=clip.w/2, y_center=clip.h/2, width=W, height=H)
                # Burn in the sentence as a subtitle using Pillow to avoid font configuration problems.
                im = Image.open(img_path).convert("RGB")
                im = im.resize((W, H))
                draw = ImageDraw.Draw(im)
                subtitle = textwrap.fill(sentence, width=24 if H > W else 52)
                box_h = min(H//3, 70 + len(subtitle.splitlines())*42)
                draw.rectangle((0, H-box_h-35, W, H), fill=(0,0,0))
                draw.multiline_text((55, H-box_h+5), subtitle, fill=(255,255,255), spacing=10, stroke_width=1)
                sub_path = os.path.join(tmp, f"sub_{i}.jpg")
                im.save(sub_path, quality=90)
                clips.append(ImageClip(sub_path).set_duration(per))
            video = concatenate_videoclips(clips, method="compose").set_audio(audio)
            out_path = os.path.join(tmp, "script_video.mp4")
            status.write("Rendering MP4 video...")
            video.write_videofile(out_path, fps=24, codec="libx264", audio_codec="aac", logger=None)
            status.update(label="Video ready!", state="complete", expanded=False)
            with open(out_path, "rb") as f:
                video_bytes = f.read()
            st.video(video_bytes)
            st.download_button("⬇️ Download MP4", data=video_bytes, file_name="script_video.mp4", mime="video/mp4", use_container_width=True)
            st.info("Note: This starter uses Wikimedia Commons images. Check image licenses before commercial use. Free hosting and voice/image services may have usage limits.")
    except Exception as e:
        st.error("The video could not be created. Try a shorter script or check the deployment logs.")
        st.caption(str(e))
