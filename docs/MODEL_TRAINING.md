# Model training

The reproducible baseline configuration is
`configs/ml/baseline.yaml`. It records dataset revision, input channels,
patch size/stride, normalization, augmentation, model, loss, optimizer,
learning rate, batch size, epochs, seed, device, threshold, and checkpoint
directory.

`train_tiny()` is a CPU-safe smoke path that saves a checkpoint and JSON
experiment manifest. Full Kuro Siwo training is intentionally not run until
the user downloads and inspects the permitted dataset. Normalization
statistics must be derived from training samples only. Validation, not the
test split, is the only source for threshold or training decisions.
