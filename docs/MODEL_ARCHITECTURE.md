# Flood segmentation baseline

The implemented baseline is a small binary U-Net. Two convolution/ReLU
encoder blocks downsample through max pooling; a bottleneck captures context;
a transposed-convolution decoder upsamples and concatenates the encoder skip
feature; a 1x1 head emits one flood logit per pixel. Sigmoid converts logits
to probabilities and a configurable validation-selected threshold produces
the binary mask.

The default input is two Sentinel-1 channels (for example VV/VH) when the
prepared dataset provides them. The model does not claim multimodal fusion.
The loss is configurable BCE + Dice; metrics are IoU, Dice, precision, and
recall.
