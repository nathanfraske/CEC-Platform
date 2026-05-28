#include "filter.h"

void median_init(median_filter_t *f)
{
    f->idx = 0;
    f->count = 0;
    for (int i = 0; i < MEDIAN_WINDOW; i++) f->buffer[i] = 0.0f;
}

float median_update(median_filter_t *f, float sample)
{
    f->buffer[f->idx] = sample;
    f->idx = (f->idx + 1) % MEDIAN_WINDOW;
    if (f->count < MEDIAN_WINDOW) f->count++;

    float tmp[MEDIAN_WINDOW];
    for (int i = 0; i < f->count; i++) tmp[i] = f->buffer[i];

    // Simple insertion-style sort (window is tiny)
    for (int i = 0; i < f->count - 1; i++) {
        for (int j = i + 1; j < f->count; j++) {
            if (tmp[j] < tmp[i]) {
                float t = tmp[i];
                tmp[i] = tmp[j];
                tmp[j] = t;
            }
        }
    }
    return tmp[f->count / 2];
}

void ema_init(ema_filter_t *f, float alpha)
{
    f->value = 0.0f;
    f->alpha = alpha;
    f->initialized = false;
}

float ema_update(ema_filter_t *f, float sample)
{
    if (!f->initialized) {
        f->value = sample;
        f->initialized = true;
    } else {
        f->value = f->alpha * sample + (1.0f - f->alpha) * f->value;
    }
    return f->value;
}

void cec_filter_init(cec_filter_t *f, float alpha)
{
    median_init(&f->median);
    ema_init(&f->ema, alpha);
}

float cec_filter_update(cec_filter_t *f, float sample)
{
    float m = median_update(&f->median, sample);
    return ema_update(&f->ema, m);
}

void cec_filter_set_alpha(cec_filter_t *f, float alpha)
{
    f->ema.alpha = alpha;
}
