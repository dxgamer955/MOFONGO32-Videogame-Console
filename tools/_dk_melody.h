#pragma once

const float dk_melodyNotes[] = {
  0.0f, 329.63f, 392.00f, 261.63f, 349.23f, 392.00f, 349.23f, 392.00f
};
const unsigned short dk_melodyDurMs[] = {
  2432, 4864, 7296, 2432, 3648, 1216, 1216, 65535
};
const int dk_melodyLen = sizeof(dk_melodyNotes) / sizeof(dk_melodyNotes[0]);
