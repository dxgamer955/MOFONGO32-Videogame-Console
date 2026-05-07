#define IRE(_x)          ((uint32_t)(((_x)+40)*255/3.3/147.5) << 8)   // 3.3V DAC
#define SYNC_LEVEL       IRE(-40)
#define BLANKING_LEVEL   IRE(0)
#define BLACK_LEVEL      IRE(7.5)
#define GRAY_LEVEL       IRE(50)
#define WHITE_LEVEL      IRE(100)

static int PIN(int x)
{
    if (x < 0) return 0;
    if (x > 255) return 255;
    return x;
}

static uint32_t rgb(int r, int g, int b)
{
    return (PIN(r) << 16) | (PIN(g) << 8) | PIN(b);
}

static int gamma_(float v, float g)
{
    if (v < 0)
        return 0;
    v = powf(v,g);
    if (v <= 0.0031308)
        return 0;
    int c = ((1.055 * powf(v, 1.0/2.4) - 0.055)*255);
    return c < 255 ? c : 255;
}

// make_yuv_palette from RGB palette
void make_yuv_palette(const char* name, const uint32_t* rgb, int len)
{
    uint32_t pal[256*2];
    uint32_t* even = pal;
    uint32_t* odd = pal + len;

    float chroma_scale = BLANKING_LEVEL/2/256;
    //chroma_scale /= 127;  // looks a little washed out
    chroma_scale /= 80;
    for (int i = 0; i < len; i++) {
        uint8_t r = rgb[i] >> 16;
        uint8_t g = rgb[i] >> 8;
        uint8_t b = rgb[i];

        float y = 0.299 * r + 0.587*g + 0.114 * b;
        float u = -0.147407 * r - 0.289391 * g + 0.436798 * b;
        float v =  0.614777 * r - 0.514799 * g - 0.099978 * b;
        y /= 255.0;
        y = (y*(WHITE_LEVEL-BLACK_LEVEL) + BLACK_LEVEL)/256;

        uint32_t e = 0;
        uint32_t o = 0;
        for (int i = 0; i < 4; i++) {
            float p = 2*M_PI*i/4 + M_PI;
            float s = sin(p)*chroma_scale;
            float c = cos(p)*chroma_scale;
            uint8_t e0 = round(y + (s*u) + (c*v));
            uint8_t o0 = round(y + (s*u) - (c*v));
            e = (e << 8) | e0;
            o = (o << 8) | o0;
        }
        *even++ = e;
        *odd++ = o;
    }

    printf("uint32_t %s_4_phase_pal[] = {\n",name);
    for (int i = 0; i < len*2; i++) {  // start with luminance map
        printf("0x%08X,",pal[i]);
        if ((i & 7) == 7)
            printf("\n");
        if (i == (len-1)) {
            printf("//odd\n");
        }
    }
    printf("};\n");

    /*
     // don't bother with phase tables
    printf("uint8_t DRAM_ATTR %s[] = {\n",name);
    for (int i = 0; i < len*(1<<PHASE_BITS)*2; i++) {
        printf("0x%02X,",yuv[i]);
        if ((i & 15) == 15)
            printf("\n");
        if (i == (len*(1<<PHASE_BITS)-1)) {
            printf("//odd\n");
        }
    }
    printf("};\n");
     */
}

// atari pal palette cc_width==4
static void make_atari_4_phase_pal(const uint16_t* lum, const float* angle)
{
    uint32_t _pal4[256*2];
    uint32_t *even = _pal4;
    uint32_t *odd = even + 256;

    float chroma_scale = BLANKING_LEVEL/2/256;
    chroma_scale *= 1.5;
    float s,c,u,v;

    for (int cr = 0; cr < 16; cr++) {
        if (cr == 0) {
            u = v = 0;
        } else {
            u = cos(angle[16-cr]);
            v = sin(angle[16-cr]);
        }
        for (int lm = 0; lm < 16; lm++) {
            uint32_t e = 0;
            uint32_t o = 0;
            for (int i = 0; i < 4; i++) {
                float p = 2*M_PI*i/4;
                s = sin(p)*chroma_scale;
                c = cos(p)*chroma_scale;
                uint8_t e0 = round(lum[lm] + (s*u) + (c*v));
                uint8_t o0 = round(lum[lm] + (s*u) - (c*v));
                e = (e << 8) | e0;
                o = (o << 8) | o0;
            }
            *even++ = e;
            *odd++ = o;
        }
    }

    printf("uint32_t atari_4_phase_pal[] = {\n");
    for (int i = 0; i < 256*2; i++) {  // start with luminance map
        printf("0x%08X,",_pal4[i]);
        if ((i & 7) == 7)
            printf("\n");
        if (i == 255) {
            printf("//odd\n");
        }
    }
    printf("};\n");
}

// lifted from atari800
static void make_atari_rgb_palette(uint32_t* palette)
{
    float start_angle =  (303.0f) * M_PI / 180.0f;
    float start_saturation = 0;
    float color_diff = 26.8 * M_PI / 180.0; // color_delay
    float scaled_black_level = (double)16 / 255.0;
    float scaled_white_level = (double)235 / 255.0;
    float contrast = 0;
    float brightness = 0;

    float luma_mult[16]={
        0.6941, 0.7091, 0.7241, 0.7401,
        0.7560, 0.7741, 0.7931, 0.8121,
        0.8260, 0.8470, 0.8700, 0.8930,
        0.9160, 0.9420, 0.9690, 1.0000};

    uint32_t linear[256];
    uint16_t _lum[16];
    float _angle[16];

    for (int cr = 0; cr < 16; cr ++) {
        float angle = start_angle + (cr - 1) * color_diff;
        float saturation = (cr ? (start_saturation + 1) * 0.175f: 0.0);
        float i = cos(angle) * saturation;
        float q = sin(angle) * saturation;

        _angle[cr] = angle + 2*M_PI*33/360;

        for (int lm = 0; lm < 16; lm ++) {
            float y = (luma_mult[lm] - luma_mult[0]) / (luma_mult[15] - luma_mult[0]);
            _lum[lm] = (y*(WHITE_LEVEL-BLACK_LEVEL) + BLACK_LEVEL)/256;

            y *= contrast * 0.5 + 1;
            y += brightness * 0.5;
            y = y * (scaled_white_level - scaled_black_level) + scaled_black_level;

            float gmma = 2.35;
            float r = (y +  0.946882*i +  0.623557*q);
            float g = (y + -0.274788*i + -0.635691*q);
            float b = (y + -1.108545*i +  1.709007*q);
            linear[(cr << 4) | lm] = rgb(r*255,g*255,b*255);
            palette[(cr << 4) | lm] = (gamma_(r,gmma) << 16) | (gamma_(g,gmma) << 8) | (gamma_(b,gmma) << 0);
        }
    }
    make_atari_4_phase_pal(_lum,_angle);
}

void make_atari_rgb_palette()
{
    uint32_t _atari_pal[256];
    make_atari_rgb_palette(_atari_pal);
    printf("const uint32_t atari_palette_rgb[256] = {\n");
    for (int i = 0; i < 256; i++) {
        printf("0x%08X,",_atari_pal[i]);
        if ((i & 7) == 7)
            printf("\n");
    }
    printf("};\n\n");
}

// derived from atari800
static void atari_palette(float start_angle = 0)
{
    float color_diff = 28.6 * M_PI / 180.0;
    int cr, lm;
    float luma_mult[16]={
        0.6941, 0.7091, 0.7241, 0.7401,
        0.7560, 0.7741, 0.7931, 0.8121,
        0.8260, 0.8470, 0.8700, 0.8930,
        0.9160, 0.9420, 0.9690, 1.0000};

    int i = 0;
    uint32_t pal[256];
    printf("const uint32_t atari_4_phase_ntsc[256] = {\n");
    for (cr = 0; cr < 16; cr ++) {
        float angle = start_angle + ((15-cr) - 1) * color_diff;

        for (lm = 0; lm < 16; lm ++) {
            //double y = luma_mult[lm]*lm*(WHITE_LEVEL-BLACK_LEVEL)/15 + BLACK_LEVEL;
            double y = lm*(WHITE_LEVEL-BLACK_LEVEL)/15 + BLACK_LEVEL;
            int p[4];
            for (int j = 0; j < 4; j++)
                p[j] = y;
            for (int j = 0; j < 4; j++)
                p[j] += sin(angle + 2*M_PI*j/4) * (cr ? BLANKING_LEVEL/2 : 0);
            uint32_t pi = 0;
            for (int j = 0; j < 4; j++)
                pi = (pi << 8) | p[j] >> 8;
            pal[i++] = pi;
            printf("0x%08X,",pi);
            if ((lm & 7) == 7)
                printf("\n");
        }
    }
    printf("};\n\n");

    // swizzled for ESP32
    #define P0 (color >> 16)
    #define P1 (color >> 8)
    #define P2 (color)
    #define P3 (color << 8)

    uint32_t color;
    // swizzed pattern for esp32 is 0 2 1 3
    printf("const uint32_t _atari_4_phase_esp[256] = {\n");
    for (int i = 0; i < 256; i++) {
        color = pal[i];
        color = (color & 0xFF0000FF) | ((color << 8) & 0x00FF0000) | ((color >> 8) & 0x0000FF00);
        printf("0x%08X,",color);
        if ((i & 7) == 7)
            printf("\n");
    }
    printf("};\n\n");
}

void setup() {
  Serial.begin(115200);
  // put your setup code here, to run once:
  //atari_palette();
  make_atari_rgb_palette();
  //atari_palette(0);

  uint32_t _atari_pal[256];
  make_atari_rgb_palette(_atari_pal);
  make_yuv_palette("atari", _atari_pal, 256);
}

void loop() {
  // put your main code here, to run repeatedly:

}
