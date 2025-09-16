import { CheckmarkIcon, XIcon } from "./icons/icons";

export const CustomCheckbox = ({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean;
  onChange?: () => void;
  disabled?: boolean;
}) => {
   const handleContainerClick = (event: any) => {
     event.stopPropagation();
   };

  const handleInputChange = (event: any) => {
    event.stopPropagation();
    if (disabled) {
      return;
    }
    onChange?.();
  };

  return (
    <label
      onClick={handleContainerClick}
      className={`flex items-center cursor-pointer ${
        disabled ? "opacity-50" : ""
      }`}
    >
      <input
        type="checkbox"
        className="hidden"
        checked={checked}
        onChange={handleInputChange}
        readOnly={onChange ? false : true}
        disabled={disabled}
      />
      <span className="relative">
        <span
          className={`block w-3 h-3 border border-border-strong rounded ${
            checked ? "bg-green-700" : disabled ? "bg-error" : "bg-background"
          } transition duration-300 ${disabled ? "bg-background" : ""}`}
        >
          {disabled && (
            <XIcon
              size={12}
              className="absolute z-[1000] top-0 left-0 fill-current text-inverted"
            />
          )}

          {checked && (
            <CheckmarkIcon
              size={12}
              className="absolute top-0 left-0 fill-current text-inverted"
            />
          )}
        </span>
      </span>
    </label>
  );
};
