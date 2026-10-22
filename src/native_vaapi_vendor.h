#ifndef UURB_VAAPI_VENDOR_H
#define UURB_VAAPI_VENDOR_H
/* The Windows adapter spoof is separate from the real encoding GPU. */
static inline int uurb_vaapi_vendor(unsigned vendor)
{
    return vendor == 0x1002 || vendor == 0x8086;
}
#endif
