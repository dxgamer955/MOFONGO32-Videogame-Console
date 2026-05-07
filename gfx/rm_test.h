#ifndef RM_TEST_H_
#define RM_TEST_H_

struct RoomObjectDef
{
  int frame;
  int x;
  int y;
  int mode; // 0=normal,1=rotated,2=scaled
  float angle;
  float scale;
};

const int rm_testBackgroundIndex = 1;
const RoomObjectDef rm_testObjects[] = {
  {0, 70, 134, 0, 0.000f, 1.000f},
  {8, 231, 126, 0, 0.000f, 1.000f},
};
const int rm_testObjectCount = sizeof(rm_testObjects) / sizeof(rm_testObjects[0]);

#endif // RM_TEST_H_