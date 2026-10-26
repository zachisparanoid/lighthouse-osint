import {
  AtSign,
  Building2,
  FileDigit,
  Globe,
  Link as LinkIcon,
  type LucideIcon,
  Mail,
  MapPin,
  Network,
  Phone,
  Router,
  Server,
  Share2,
  ShieldAlert,
  ShieldCheck,
  User,
} from "lucide-react";

import { ENTITY_META, type EntityType } from "@lighthouse/shared-types";

const ICONS: Record<string, LucideIcon> = {
  Globe,
  Network,
  Server,
  Mail,
  AtSign,
  User,
  Building2,
  Phone,
  Link: LinkIcon,
  Router,
  ShieldCheck,
  Share2,
  ShieldAlert,
  FileDigit,
  MapPin,
};

export function entityColor(type: EntityType | string): string {
  return ENTITY_META[type as EntityType]?.color ?? "#94A3B8";
}

export function entityLabel(type: EntityType | string): string {
  return ENTITY_META[type as EntityType]?.label ?? String(type);
}

export function entityIcon(type: EntityType | string): LucideIcon {
  const meta = ENTITY_META[type as EntityType];
  return (meta && ICONS[meta.icon]) || Globe;
}

export function entityIsMono(type: EntityType | string): boolean {
  return ENTITY_META[type as EntityType]?.mono ?? false;
}
