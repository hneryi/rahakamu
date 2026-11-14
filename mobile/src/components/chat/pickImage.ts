/**
 * Image capture for the vision feature ("snap a price tag → can I afford this?").
 * Returns a compressed JPEG as base64 for `image_base64` in POST /api/chat.
 * On native the user chooses camera or library; on web the file picker opens.
 */
import * as ImagePicker from 'expo-image-picker';
import { Alert, Platform } from 'react-native';

import { translate } from '@/i18n';
import { useSession } from '@/store/session';

export type PickedImage = { uri: string; base64: string };

const OPTS: ImagePicker.ImagePickerOptions = { mediaTypes: ['images'], base64: true, quality: 0.4, allowsEditing: false, exif: false };

async function fromCamera(): Promise<PickedImage | null> {
  const perm = await ImagePicker.requestCameraPermissionsAsync();
  if (!perm.granted) return null;
  const res = await ImagePicker.launchCameraAsync(OPTS);
  return toPicked(res);
}

async function fromLibrary(): Promise<PickedImage | null> {
  const res = await ImagePicker.launchImageLibraryAsync(OPTS);
  return toPicked(res);
}

function toPicked(res: ImagePicker.ImagePickerResult): PickedImage | null {
  if (res.canceled || !res.assets?.[0]) return null;
  const a = res.assets[0];
  let base64 = a.base64 ?? '';
  // Web may return a data URI in `uri` and no base64 field.
  if (!base64 && a.uri.startsWith('data:')) base64 = a.uri.split(',')[1] ?? '';
  if (!base64) return null;
  return { uri: a.uri, base64 };
}

export async function pickImage(): Promise<PickedImage | null> {
  try {
    if (Platform.OS === 'web') return await fromLibrary();
    const locale = useSession.getState().locale;
    return await new Promise<PickedImage | null>((resolve) => {
      Alert.alert(translate(locale, 'chat.attach'), undefined, [
        { text: translate(locale, 'chat.camera'), onPress: () => fromCamera().then(resolve, () => resolve(null)) },
        { text: translate(locale, 'chat.library'), onPress: () => fromLibrary().then(resolve, () => resolve(null)) },
        { text: translate(locale, 'common.cancel'), style: 'cancel', onPress: () => resolve(null) },
      ]);
    });
  } catch {
    return null;
  }
}
