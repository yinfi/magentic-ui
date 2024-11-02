import { Modal, Input, Button, message } from "antd";
import { setLocalStorage } from "./utils";
import { appContext } from "../hooks/provider";
import * as React from "react";

type SignInModalProps = {
  isVisible: boolean;
  onClose: () => void;
};

const SignInModal = ({ isVisible, onClose }: SignInModalProps) => {
  const { user, setUser } = React.useContext(appContext);
  const [email, setEmail] = React.useState(user?.email || "default");

  const isAlreadySignedIn = !!user?.email;

  const handleEmailChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setEmail(e.target.value);
  };

  const handleSignIn = () => {
    const trimmedEmail = email.trim();
    if (!trimmedEmail) {
      message.error("Username cannot be empty");
      return;
    }
    setUser({ ...user, email: trimmedEmail, name: trimmedEmail });
    setLocalStorage("user_email", trimmedEmail);
    onClose();
  };

  return (
    <Modal
      title="Enter your username. A change of username will create a new profile."
      open={isVisible}
      footer={null}
      closable={isAlreadySignedIn}
      maskClosable={isAlreadySignedIn}
      onCancel={isAlreadySignedIn ? onClose : undefined}
    >
      <div className="mb-4">
        <Input
          type="text"
          placeholder="Enter your username"
          value={email}
          onChange={handleEmailChange}
          className="shadow-sm"
        />
      </div>
      <div className="flex justify-center">
        <Button
          type="primary"
          onClick={handleSignIn}
          className="flex items-center justify-center text-white hover:opacity-90 transition-opacity font-semibold"
        >
          Sign In
        </Button>
      </div>
    </Modal>
  );
};

export default SignInModal;
