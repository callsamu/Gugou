import type { JSX, VNode } from "preact";

declare module "preact-router" {
  interface LinkProps extends JSX.HTMLAttributes<HTMLAnchorElement> {
    href: string;
  }

  export function Link(props: LinkProps): VNode;
}
