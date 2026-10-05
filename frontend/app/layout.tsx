import type { Metadata } from "next";
import { SocketProvider } from "../lib/socket/provider";
import "./globals.css";
export const metadata: Metadata = { title: "Boardgame · Realtime check" };
export default function Layout({ children }: { children: React.ReactNode }) {
  return <html lang="vi"><body><SocketProvider>{children}</SocketProvider></body></html>;
}
