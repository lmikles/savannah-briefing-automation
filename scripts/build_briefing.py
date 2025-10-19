import os, io, json, yaml, datetime
import boto3
from pydub import AudioSegment
from pydub.generators import Sine
from scripts.utils import fetch_source, compress_items, build_script, extract_weather_from_json

def utc_iso(dt=None):
    return (dt or datetime.datetime.utcnow()).strftime("%Y-%m-%dT%H:%M:%S.0Z")

def prepend_chime(speech: AudioSegment):
    tone = Sine(880).to_audio_segment(duration=500).fade_in(50).fade_out(50).apply_gain(-9)
    pad = AudioSegment.silent(duration=150)
    return tone + pad + speech

def synthesize_polly(text, voice, region):
    polly = boto3.client("polly", region_name=region)
    try:
        resp = polly.synthesize_speech(Text=text, VoiceId=voice, Engine="neural", OutputFormat="mp3")
    except Exception:
        resp = polly.synthesize_speech(Text=text, VoiceId=voice, OutputFormat="mp3")
    audio_stream = resp["AudioStream"].read()
    return AudioSegment.from_file(io.BytesIO(audio_stream), format="mp3")

def upload_s3(mp3_bytes, bucket, key, region):
    s3 = boto3.client("s3", region_name=region)
    s3.put_object(Bucket=bucket, Key=key, Body=mp3_bytes, ContentType="audio/mpeg", ACL="public-read")
    return f"https://{bucket}.s3.{region}.amazonaws.com/{key}"

def main():
    # load config
    with open("config.yaml","r") as f:
        cfg = yaml.safe_load(f)

    use_latest = bool(cfg.get("use_latest_alias", True))
    latest_name = cfg.get("latest_filename","latest.mp3")
    dated_tpl = cfg.get("dated_filename_template","{date}.mp3")
    target_minutes = int(cfg.get("target_duration_minutes", 10))

    # gather sources
    civic_pool, culture_pool, weather_text = [], [], ""
    for src in cfg["sources"]:
        items = fetch_source(src)
        if "weather" in src["name"].lower():
            if items and items[0].get("desc"):
                weather_text = extract_weather_from_json(items[0]["desc"])
            continue
        # crude route: city/wtoc/wsav/wjcl to civic; rest to culture
        if any(k.lower() in src["name"].lower() for k in ["city","wtoc","wsav","wjcl"]):
            civic_pool.extend(items)
        else:
            culture_pool.extend(items)

    civic = compress_items(civic_pool, limit=8)
    culture = compress_items(culture_pool, limit=8)

    script_text = build_script(weather_text, civic, culture)

    # synthesize speech
    voice = os.environ.get("POLLY_VOICE","Joanna")
    region = os.environ.get("AWS_REGION","us-east-2")
    speech = synthesize_polly(script_text, voice, region)
    final_audio = prepend_chime(speech)

    # export mp3
    buf = io.BytesIO()
    final_audio.export(buf, format="mp3", bitrate="128k")
    mp3_bytes = buf.getvalue()

    # destination
    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    prefix = (os.environ.get("S3_PREFIX","savannah-briefings") or "savannah-briefings").strip("/")
    key = f"{prefix}/{latest_name if use_latest else dated_tpl.format(date=today)}"
    bucket = os.environ["S3_BUCKET"]

    # upload
    url = upload_s3(mp3_bytes, bucket, key, region)

    # write feed JSON in this repo (served by Pages)
    feed = [
        {
            "uid": f"savannah-{'latest' if use_latest else today}",
            "updateDate": utc_iso(),
            "titleText": "Savannah Daily Briefing",
            "mainText": "",
            "streamUrl": url,
            "redirectionUrl": "https://YOUR_USERNAME.github.io/savannah-briefing-automation/"
        }
    ]
    with open("savannah-daily-briefing-feed.json","w") as f:
        json.dump(feed, f, indent=2)

    with open("latest-script.txt","w") as f:
        f.write(script_text)

    print("Published:", url)

if __name__ == "__main__":
    main()
