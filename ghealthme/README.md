# ghealthme
Google Health API Integration for MeasureMe.

This project is part of the MeasureMe ecosystem. It provides the standalone command-line ingestors, Flask webhooks for pushing notifications over Cloudflare Tunnels, and background worker queues to process Google Health API data into the core database.

## Implementation
As of June 2026, the Google Health API (Health Connect REST) has transitioned out of the beta deprecation period. While some core metrics are now reliably available, many secondary metrics remain unsupported in the REST discovery document.

From the [web page](https://developers.google.com/health/migration):
*To ensure a seamless experience for your users, we recommend waiting until the end of May 2026 to officially launch your integration to align with legacy Fitbit account deprecation.*

| Function                         | 2026-04-01 | 2026-06-09 |
| :------------------------------- | :--------: | :--------: |
| steps                            |     ✅     |     ✅     |
| sleep                            |     ✅     |     ✅     |
| exercise                         |     ✅     |     ✅     |
| weight                           |     ✅     |     ✅     |
| height                           |     -      |     ✅     |
| food                             |     -      |     ✅     |
| altitude                         |     ✅     |     ✅     |
| distance                         |     ✅     |     ✅     |
| floors                           |     ❌     |     ❌     |
| heartRate                        |     ❌     |     ✅     |
| dailyRestingHeartRate            |     ❌     |     ✅     |
| dailyHeartRateVariability        |     ❌     |     ✅     |
| bodyFat                          |     ❌     |     ✅     |
| activeZoneMinutes                |     ❌     |     ✅     |
| heartRateVariability             |     ❌     |     ✅     |
| dailySleepTemperatureDerivations |     ❌     |     ✅     |
| sedentaryPeriod                  |     ❌     |     ✅     |
| runVo2Max                        |     ❌     |     ✅     |
| oxygenSaturation                 |     ❌     |     ✅     |
| dailyOxygenSaturation            |     ❌     |     ✅     |
| activityLevel                    |     ❌     |     ✅     |
| vo2Max                           |     ❌     |     ✅     |
| dailyVo2Max                      |     ❌     |     ✅     |
| dailyHeartRateZones              |     ❌     |     ✅     |
| hydrationLog                     |     ❌     |     ✅     |
| timeInHeartRateZone              |     ❌     |     ✅     |
| activeMinutes                    |     ❌     |     ✅     |
| respiratoryRateSleepSummary      |     ❌     |     ✅     |
| dailyRespiratoryRate             |     ❌     |     ✅     |
