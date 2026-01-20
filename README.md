# Parking Detection Workflow

Pipeline detekcji zajętości parkingów oparty o **Argo Workflows** - ortofotomapy z WMTS Geoportal + YOLO.

## Architektura

```
Input (parkings JSON)
        │
        ▼
   ┌─────────┐
   │ Fan-out │ (withParam)
   └────┬────┘
        │
   ┌────┴────┬────────┐
   ▼         ▼        ▼
┌──────┐ ┌──────┐ ┌──────┐
│Park 1│ │Park 2│ │Park N│  (parallel)
└──┬───┘ └──┬───┘ └──┬───┘
   │        │        │
   ▼        ▼        ▼
┌─────────────────────────┐
│     WMTS Fetcher        │ → image.jpg + meta.json
│     (EPSG:4326)         │
└───────────┬─────────────┘
            ▼
┌─────────────────────────┐
│    YOLO Inference       │ → detections.json
│    (yolo26n.pt)         │
└───────────┬─────────────┘
            ▼
┌─────────────────────────┐
│    Geo Converter        │ → vehicles.geojson (Polygon bboxes)
│    (pixel → lonlat)     │
└───────────┬─────────────┘
            │
            └────────┐
                     ▼
              ┌────────────┐
              │ Aggregator │ (Fan-in)
              └─────┬──────┘
                    │
           ┌────────┴────────┐
           ▼                 ▼
 all_parkings.geojson    stats.csv
```

## Struktura projektu

```
containers/
├── wmts-fetcher/     # Pobieranie ortofotomap
│   ├── config.py     # Settings + logging
│   ├── fetch_tiles.py
│   └── Dockerfile
├── yolo-inference/   # Detekcja pojazdów
│   ├── config.py
│   ├── detect.py
│   └── Dockerfile
├── geo-converter/    # Konwersja pixel bbox → lon/lat Polygon
│   ├── config.py
│   ├── convert.py
│   └── Dockerfile
└── aggregator/       # Agregacja wyników
    ├── config.py
    ├── aggregate.py
    └── Dockerfile

workflow/
└── parking-detection.yaml
```

## Konfiguracja przez zmienne środowiskowe

### WMTS Fetcher
| Zmienna | Opis | Domyślnie |
|---------|------|-----------|
| `PARKING_JSON` | JSON z name i bbox | `{"name":"default","bbox":[...]}` |
| `OUTPUT_DIR` | Katalog wyjściowy | `/data/output` |
| `ZOOM` | Poziom zoomu (0-16) | auto |
| `LOG_LEVEL` | Poziom logowania | `INFO` |

### YOLO Inference
| Zmienna | Opis | Domyślnie |
|---------|------|-----------|
| `IMAGE_PATH` | Ścieżka do obrazu | `/data/input/image.jpg` |
| `MODEL_PATH` | Ścieżka do modelu | `/model/yolo26n.pt` |
| `PARKING_NAME` | Nazwa parkingu | `` |
| `OUTPUT_DIR` | Katalog wyjściowy | `/data/output` |
| `CONFIDENCE` | Próg pewności | `0.25` |

### Geo Converter
| Zmienna | Opis | Domyślnie |
|---------|------|-----------|
| `DETECTIONS_PATH` | Plik z detekcjami | `/data/input/detections.json` |
| `META_PATH` | Plik z metadanymi | `/data/input/meta.json` |
| `OUTPUT_DIR` | Katalog wyjściowy | `/data/output` |

### Aggregator
| Zmienna | Opis | Domyślnie |
|---------|------|-----------|
| `INPUT_DIR` | Katalog z GeoJSON | `/data/input` |
| `OUTPUT_DIR` | Katalog wyjściowy | `/data/output` |

## Uruchomienie lokalne

```bash
# WMTS fetcher
PARKING_JSON='{"name":"test","bbox":[20.996,52.229,21.001,52.232]}' \
OUTPUT_DIR=./output ZOOM=14 \
python containers/wmts-fetcher/fetch_tiles.py

# YOLO inference
IMAGE_PATH=./output/test.jpg MODEL_PATH=./yolo26n.pt \
PARKING_NAME=test OUTPUT_DIR=./output \
python containers/yolo-inference/detect.py

# Geo converter
DETECTIONS_PATH=./output/test_detections.json \
META_PATH=./output/test_meta.json OUTPUT_DIR=./output \
python containers/geo-converter/convert.py

# Aggregator
INPUT_DIR=./output OUTPUT_DIR=./output \
python containers/aggregator/aggregate.py
```

## Budowanie obrazów Docker

```bash
docker build -t parking-detection/wmts-fetcher:latest containers/wmts-fetcher/
docker build -t parking-detection/yolo-inference:latest containers/yolo-inference/
docker build -t parking-detection/geo-converter:latest containers/geo-converter/
docker build -t parking-detection/aggregator:latest containers/aggregator/
```

## Uruchomienie na Kubernetes (Argo Workflows)

```bash
# Utwórz ConfigMap z modelem
kubectl -n argo create configmap yolo-model --from-file=yolo26n.pt

# Uruchom workflow
kubectl apply -f workflow/parking-detection.yaml

# Monitoruj
kubectl -n argo get workflows
kubectl -n argo logs -l workflows.argoproj.io/workflow -f
```

## Format wyjściowy

### all_parkings.geojson
```json
{
  "type": "FeatureCollection",
  "properties": {
    "total_parkings": 2,
    "total_vehicles": 127,
    "crs": "EPSG:4326"
  },
  "features": [
    {
      "type": "Feature",
      "properties": {"class": "car", "confidence": 0.87, "parking": "parking1"},
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[20.998, 52.230], [20.999, 52.230], [20.999, 52.231], [20.998, 52.231], [20.998, 52.230]]]
      }
    }
  ]
}
```

### stats.csv
```csv
parking,vehicles,timestamp
parking1,47,2026-01-20T15:30:00
```
