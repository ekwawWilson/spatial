import BingMaps from "ol/source/BingMaps";
import TileWMS from "ol/source/TileWMS";
import XYZ from "ol/source/XYZ";
import { describe, expect, it, vi } from "vitest";

import { basemapSource } from "./basemap";
import type { BasemapConfig } from "./types";

const base: BasemapConfig = {
  id: 1,
  name: "Test",
  kind: "xyz",
  url: "https://tile.example.com/{z}/{x}/{y}.png",
  layers: "",
  attribution: "© Example",
  min_zoom: 0,
  max_zoom: 19,
};

describe("basemapSource", () => {
  it("builds XYZ sources", async () => {
    const source = await basemapSource(base);
    expect(source).toBeInstanceOf(XYZ);
    expect((source as XYZ).getUrls()).toEqual(["https://tile.example.com/{z}/{x}/{y}.png"]);
  });

  it("builds WMS sources with the layer names", async () => {
    const source = await basemapSource({ ...base, kind: "wms", url: "https://wms.example.com/wms", layers: "ortho2025" });
    expect(source).toBeInstanceOf(TileWMS);
    expect((source as TileWMS).getParams().LAYERS).toBe("ortho2025");
  });

  it("builds Bing sources with the key", async () => {
    const source = await basemapSource({ ...base, kind: "bing", url: "", layers: "Aerial", key: "K" });
    expect(source).toBeInstanceOf(BingMaps);
  });

  it("explains an unreachable WMTS capabilities document", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response("nope", { status: 404 }));
    await expect(
      basemapSource({ ...base, kind: "wmts", url: "https://wmts.example.com/caps.xml", layers: "x" }, fetchImpl),
    ).rejects.toThrow("Couldn't read the WMTS capabilities (HTTP 404)");
  });
});

describe("the district's own imagery", () => {
  it("is recognised by its address", async () => {
    const { isOwnImagery } = await import("./basemap");
    expect(isOwnImagery("/api/imagery/3/tiles/{z}/{x}/{y}.png")).toBe(true);
    expect(isOwnImagery("https://tile.openstreetmap.org/{z}/{x}/{y}.png")).toBe(false);
  });

  it("loads its tiles through the signed-in API, not as plain images", async () => {
    const own = { ...base, url: "/api/imagery/3/tiles/{z}/{x}/{y}.png" };
    const withLoader = (await basemapSource(own, fetch, async () => null)) as XYZ;
    const plain = (await basemapSource(base, fetch, async () => null)) as XYZ;
    expect(withLoader.getTileLoadFunction()).not.toBe(plain.getTileLoadFunction());
  });
});
