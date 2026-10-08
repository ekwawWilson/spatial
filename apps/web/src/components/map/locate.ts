import Feature from "ol/Feature";
import type OlMap from "ol/Map";
import Control from "ol/control/Control";
import { Circle as CircleGeometry, Point } from "ol/geom";
import VectorLayer from "ol/layer/Vector";
import { fromLonLat } from "ol/proj";
import VectorSource from "ol/source/Vector";
import { Circle as CircleStyle, Fill, Stroke, Style } from "ol/style";

/** Plain words for why the position couldn't be found. */
export function locateProblem(error: { code: number }): string {
  if (error.code === 1) return "Location is blocked for this site. Allow it in the browser's address bar, then try again.";
  if (error.code === 3) return "Finding your location took too long. Try again, ideally near a window or outdoors.";
  return "Your location couldn't be found on this device.";
}

/**
 * A "My location" button for the map: shows where the device is, with its
 * accuracy as a circle, and moves the map there. The position stays on this
 * device; nothing is sent to the server.
 */
export function installLocate(map: OlMap, onProblem: (message: string | null) => void): () => void {
  const source = new VectorSource();
  const layer = new VectorLayer({
    source,
    zIndex: 10_001,
    style: (feature) =>
      feature.getGeometry() instanceof Point
        ? new Style({ image: new CircleStyle({ radius: 7, fill: new Fill({ color: "#1a73e8" }), stroke: new Stroke({ color: "#fff", width: 2 }) }) })
        : new Style({ fill: new Fill({ color: "rgba(26, 115, 232, 0.12)" }), stroke: new Stroke({ color: "rgba(26, 115, 232, 0.5)", width: 1 }) }),
  });
  map.addLayer(layer);

  const button = document.createElement("button");
  button.type = "button";
  button.title = "My location";
  button.setAttribute("aria-label", "My location");
  button.textContent = "◎";
  const element = document.createElement("div");
  element.className = "map-locate ol-unselectable ol-control";
  element.appendChild(button);
  const control = new Control({ element });
  map.addControl(control);

  button.addEventListener("click", () => {
    onProblem(null);
    if (!("geolocation" in navigator)) {
      onProblem("This browser can't tell the map where you are.");
      return;
    }
    button.disabled = true;
    navigator.geolocation.getCurrentPosition(
      (position) => {
        button.disabled = false;
        const centre = fromLonLat([position.coords.longitude, position.coords.latitude]);
        // Web Mercator stretches distances away from the equator; Ghana is close enough.
        const accuracy = new CircleGeometry(centre, position.coords.accuracy);
        source.clear();
        source.addFeatures([new Feature(accuracy), new Feature(new Point(centre))]);
        map.getView().fit(accuracy.getExtent(), { maxZoom: 17, padding: [60, 60, 60, 60], duration: 300 });
      },
      (error) => {
        button.disabled = false;
        onProblem(locateProblem(error));
      },
      { enableHighAccuracy: true, timeout: 20_000, maximumAge: 30_000 },
    );
  });

  return () => {
    map.removeControl(control);
    map.removeLayer(layer);
  };
}
