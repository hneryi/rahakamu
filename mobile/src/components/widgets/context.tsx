/**
 * Context that lets generated widgets talk back to their host screen.
 * In chat, `onPrompt` sends a follow-up message and `onCelebrate` makes the
 * character celebrate; on other screens the defaults open the chat instead.
 */
import { createContext, useContext } from 'react';

import { openChat } from '@/lib/chatNav';

export type WidgetHost = {
  onPrompt: (text: string) => void;
  onCelebrate: () => void;
};

export const WidgetContext = createContext<WidgetHost>({
  onPrompt: (text) => openChat(text),
  onCelebrate: () => {},
});

export const useWidgetHost = () => useContext(WidgetContext);
