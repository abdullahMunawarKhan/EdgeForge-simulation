export const DEFAULT_SCENARIO_PREVIEW = Object.freeze({
  weather: Object.freeze({
    precipitation: 70,
    fog_density: 40,
    wetness: 80,
  }),
  traffic_density: 'Moderate',
  lighting: 'Day',
})

export function createScenarioPreviewPayload(configuration) {
  return {
    weather: {
      precipitation: Number(configuration.weather.precipitation),
      fog_density: Number(configuration.weather.fog_density),
      wetness: Number(configuration.weather.wetness),
    },
    traffic_density: configuration.traffic_density,
    lighting: configuration.lighting,
  }
}
