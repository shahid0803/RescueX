# Satellite scene selection

An event date is a boundary, not an image. Images acquired before midnight
UTC on the event date are candidates for **before**; images after midnight
UTC are candidates for **after**. Images on the event date are therefore not
silently treated as either role by the selection boundary.

Candidates must intersect the AOI. The result preserves footprints and does
not claim full coverage when only an intersection is known. The current
implementation ranks coverage first, then temporal proximity, cloud cover
when available, and stable scene ID.

For Sentinel-1, pair selection additionally prefers the same relative orbit
and orbit direction. `validate_sentinel1_pair` checks mission, processing
level, spatial overlap, temporal relationship, and AOI overlap. Different or
unknown orbit metadata produces a warning and prevents a strong pair claim;
it is not treated as proof that a pair is pixel-compatible. A 12-day
separation may be useful for a case study but is never a hard-coded validity
rule.

For Sentinel-2, cloud cover is retained and can be configured in the search
request. Cloudy scenes are not automatically deleted because later
preprocessing may use cloud masks or reject them based on the actual AOI.

Selection is deterministic and explainable. The response contains candidate
lists, selected scenes, reasons, warnings, compatibility fields, and query
timestamp. If either side has no candidate, the response contains no fake
scene and leaves selection fields null.
