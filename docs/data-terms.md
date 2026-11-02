# Data terms

[Back to the README](../README.md)

## Data terms

What I found when I checked in October 2026. This is my reading of public pages, not legal advice.

- **FastF1.** The code is MIT-licensed. Its [documentation](https://docs.fastf1.dev/index.html) says it is unofficial and not associated with the Formula 1 companies, and that F1 and related marks are trade marks of Formula One Licensing B.V. It grants no rights to the data itself.
- **Formula 1.** The [legal notices](https://formula1.com/en/information/legal-notices.7egvZU48hzrypubGBNcQKt) limit site content to personal, non-commercial use and forbid distributing, copying, extracting or commercially exploiting it, and list live timing data and historical race data as covered material. The F1 App terms say results, timing data and certain other content are copyright Formula One World Championship Limited. Those terms are written for F1's own site and app, not for the feed FastF1 reads, but the position on timing data is clear.
- **Jolpica.** I could not find a statement of its data licence or terms; FastF1's documentation says only that Jolpica's rate limits apply.

Where that leaves this repository: the raw feed data, the lake and the database are not committed; they are generated locally from your own ingest. The repository does include derived JSON for the web app: lap and sector times, season results, pit-stop scores and predictor scores. That is a risk I have not resolved. I found no permission to publish timing data, and the project is for personal, non-commercial analysis. If a rights holder objects, or once I find clearer terms, those files come out. Anyone running the project should read the same terms.
