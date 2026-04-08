declare global {
  interface Window {
    __deepAuditTranslatorDomCompatInstalled__?: boolean;
  }
}

function isDomNotFoundError(error: unknown): error is DOMException {
  return error instanceof DOMException && error.name === "NotFoundError";
}

export function installTranslatorDomCompatPatch() {
  if (
    typeof window === "undefined" ||
    window.__deepAuditTranslatorDomCompatInstalled__
  ) {
    return;
  }

  window.__deepAuditTranslatorDomCompatInstalled__ = true;

  const nativeRemoveChild = Node.prototype.removeChild;
  const nativeInsertBefore = Node.prototype.insertBefore;

  Node.prototype.removeChild = function <T extends Node>(child: T): T {
    const actualParent = child.parentNode;

    if (actualParent && actualParent !== this) {
      nativeRemoveChild.call(actualParent, child);
      return child;
    }

    try {
      return nativeRemoveChild.call(this, child) as T;
    } catch (error) {
      if (isDomNotFoundError(error)) {
        const fallbackParent = child.parentNode;
        if (fallbackParent) {
          nativeRemoveChild.call(fallbackParent, child);
        }
        return child;
      }

      throw error;
    }
  };

  Node.prototype.insertBefore = function <T extends Node>(
    newNode: T,
    referenceNode: Node | null,
  ): T {
    if (referenceNode && referenceNode.parentNode !== this) {
      return this.appendChild(newNode) as T;
    }

    try {
      return nativeInsertBefore.call(this, newNode, referenceNode) as T;
    } catch (error) {
      if (isDomNotFoundError(error)) {
        return this.appendChild(newNode) as T;
      }

      throw error;
    }
  };
}
