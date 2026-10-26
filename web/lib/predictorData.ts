"use client";

import { useJson } from "./data";
import type { ScoreDoc, StopsDoc } from "./predictor";

export const useScore = () => useJson<ScoreDoc>("/predictor-data/score.json");
export const useStops = () => useJson<StopsDoc>("/predictor-data/stops.json");
