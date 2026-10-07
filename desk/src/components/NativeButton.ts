import { h, type FunctionalComponent } from "vue";

/**
 * A real <button> for `<component :is>`. Passing the string "button" there resolves to
 * frappe-ui's globally registered Button (Vue prefers a registered component over the
 * native tag), which renders its own label and drops the slot content.
 */
const NativeButton: FunctionalComponent = (_, { attrs, slots }) =>
  h("button", attrs, slots.default?.());
NativeButton.inheritAttrs = false;

export default NativeButton;
