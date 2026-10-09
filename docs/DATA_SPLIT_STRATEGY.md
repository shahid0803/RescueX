# Geographic data split strategy

The split unit is a scene/region group, not an individual neighboring tile.
`geographic_split` shuffles region identifiers with a recorded seed and
assigns whole groups to train, validation, or test. It prevents a scene from
appearing in multiple splits and leaves the final Trishuli evaluation outside
the training manifest.

Default target proportions are 70/15/15 by region, subject to small-dataset
rounding. The actual region counts must be written into an experiment
manifest. If a downloaded dataset lacks reliable region metadata, the safe
fallback is scene ID grouping and the limitation must be reported; no claim
of geographic independence is made.
